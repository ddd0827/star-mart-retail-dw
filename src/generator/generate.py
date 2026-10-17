"""数据模拟总入口。

用法（项目根目录）：
    .venv\\Scripts\\python.exe -m src.generator.generate
    .venv\\Scripts\\python.exe -m src.generator.generate --sample-days 5 --members 3000 --skus 300
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common.config import Config
from src.common.io_utils import write_json
from src.common.logger import get_logger, setup_logger
from src.generator import inventory, online, orders, traffic
from src.generator.master_data import build_master
from src.generator.raw_writer import RawWriter


def parse_args() -> argparse.Namespace:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="星选生活连锁零售模拟数据生成")
    parser.add_argument("--start-date", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--sample-days", type=int, help="仅生成最近 N 天（用于快速验证）")
    parser.add_argument("--members", type=int, help="会员数量覆盖")
    parser.add_argument("--skus", type=int, help="SKU 数量覆盖")
    parser.add_argument("--sessions-per-day", type=int, help="每日线上会话数覆盖")
    parser.add_argument("--seed", type=int, help="随机种子覆盖")
    parser.add_argument("--keep-raw", action="store_true", help="保留已有 raw 目录（默认清理后重建）")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> Config:
    overrides: dict = {}
    dates = {}
    if args.end_date:
        dates["end"] = args.end_date
    if args.start_date:
        dates["start"] = args.start_date
    cfg = Config(overrides={"dates": dates} if dates else None)
    if args.sample_days:
        start = cfg.end_date - timedelta(days=args.sample_days - 1)
        overrides.setdefault("dates", {"start": start.isoformat()})
    if args.members:
        overrides.setdefault("scale", {})["members"] = args.members
    if args.skus:
        overrides.setdefault("scale", {})["skus"] = args.skus
    if args.sessions_per_day:
        overrides.setdefault("scale", {})["online_sessions_per_day"] = args.sessions_per_day
    if args.seed:
        overrides.setdefault("project", {})["seed"] = args.seed
    if overrides:
        merged = {}
        for key, value in overrides.items():
            merged[key] = value
        cfg = cfg.with_overrides(merged)
    return cfg


def _write_daily_orders(writer: RawWriter, config: Config, orders_df, details, payments, refunds, canceled_ids):
    for dt in config.dt_list():
        od = orders_df[orders_df["dt"] == dt]
        if len(od):
            writer.write_daily("order_info", od, dt)
        det = details[details["dt"] == dt]
        if len(det):
            writer.write_daily("order_detail", det, dt, canceled_order_ids=canceled_ids)
        pay = payments[payments["dt"] == dt]
        if len(pay):
            writer.write_daily("payment_info", pay, dt)
        ref = refunds[refunds["dt"] == dt] if len(refunds) else refunds
        if len(ref):
            writer.write_daily("refund_info", ref, dt)


def _validate(orders_df, details, refunds, stats: dict) -> dict:
    paid = orders_df[orders_df["paid_amount"] > 0]
    line_sum = details.groupby("order_id")["line_amount"].sum()
    merged = paid[["order_id", "paid_amount", "shipping_fee"]].merge(
        line_sum.rename("line_sum"), left_on="order_id", right_index=True, how="left"
    )
    mismatch = int(((merged["line_sum"].fillna(0) + merged["shipping_fee"] - merged["paid_amount"]).abs() > 0.05).sum())
    over_refund = 0
    if len(refunds):
        m = refunds.merge(details[["order_id", "line_id", "line_amount"]], on=["order_id", "line_id"], how="left", suffixes=("", "_d"))
        over_refund = int((m["refund_amount"] > m["line_amount"] + 0.02).sum())
    checks = {
        "paid_order_amount_line_mismatch": mismatch,
        "refund_over_line_amount": over_refund,
        "paid_orders_nonempty": int(len(paid)),
        "stats": stats,
    }
    return checks


def main() -> int:
    args = parse_args()
    config = build_config(args)
    config.ensure_dirs()
    logger = setup_logger(config.path("run_log"))
    logger.info("=" * 70)
    logger.info("开始生成模拟数据：%s ~ %s，种子=%s", config.start_date, config.end_date, config.seed)
    logger.info("规模：会员=%s, SKU=%s, 每日线上会话=%s",
                config.scale["members"], config.scale["skus"], config.scale["online_sessions_per_day"])

    if not args.keep_raw:
        raw_dir = config.path("raw")
        if raw_dir.exists():
            logger.info("清理旧 raw 目录: %s", raw_dir)
            shutil.rmtree(raw_dir)
    config.ensure_dirs()

    t0 = time.time()
    rng_master = np.random.default_rng(config.seed + 1)
    rng_traffic = np.random.default_rng(config.seed + 2)
    rng_online = np.random.default_rng(config.seed + 3)
    rng_orders = np.random.default_rng(config.seed + 4)
    rng_inventory = np.random.default_rng(config.seed + 5)
    rng_dirty = np.random.default_rng(config.seed + 6)
    writer = RawWriter(config, rng_dirty, enabled=bool(config.get("generator.dirty_injection", True)))

    timings = {}

    # 1. 主数据
    t = time.time()
    logger.info("[1/5] 生成主数据（门店/商品/会员/品牌/品类/供应商/活动）...")
    master = build_master(config, rng_master)
    for table, key in (
        ("store_info", "stores"), ("supplier_info", "suppliers"), ("brand_info", "brands"),
        ("category_info", "categories"), ("product_info", "products"), ("member_info", "members"),
        ("channel_info", "channels"), ("promotion_info", "promotions"),
    ):
        writer.write_dim(table, master[key])
    logger.info("主数据完成：门店(含线上仓)=%d, SKU=%d, 会员=%d, 品类=%d, 品牌=%d",
                len(master["stores"]), len(master["products"]), len(master["members"]),
                len(master["categories"]), len(master["brands"]))
    timings["master"] = round(time.time() - t, 2)

    # 2. 客流
    t = time.time()
    logger.info("[2/5] 生成门店日客流...")
    traffic_df = traffic.generate_store_traffic(config, master, rng_traffic)
    for dt, grp in traffic_df.groupby("dt", sort=False):
        writer.write_daily("store_traffic_daily", grp, dt)
    timings["traffic"] = round(time.time() - t, 2)

    # 3. 线上会话与行为日志
    t = time.time()
    logger.info("[3/5] 生成线上会话、行为事件与线上订单种子...")
    online_orders, online_daily = online.generate_online(config, master, rng_online, writer)
    online_stats = {
        "online_sessions": int(sum(v.get("online_session", 0) for v in online_daily.values())),
        "behavior_events": int(sum(v.get("behavior_event", 0) for v in online_daily.values())),
        "online_paid_orders": int(len(online_orders)),
    }
    logger.info("线上完成：会话=%d, 事件=%d, 线上支付订单=%d",
                online_stats["online_sessions"], online_stats["behavior_events"], online_stats["online_paid_orders"])
    timings["online"] = round(time.time() - t, 2)

    # 4. 交易域
    t = time.time()
    logger.info("[4/5] 生成订单、订单行、支付、退款/退货与门店目标...")
    order_df, details, payments, refunds, demand, returns, targets, order_stats, canceled_ids = orders.generate_orders(
        config, master, traffic_df, online_orders, rng_orders
    )
    _write_daily_orders(writer, config, order_df, details, payments, refunds, canceled_ids)
    if len(targets):
        writer.write_dim("store_sales_target", targets)
    logger.info("交易完成：有效订单=%d（线下=%d, 线上=%d），GMV=%.2f 万元，AOV=%.2f 元，退款订单=%d",
                order_stats["paid_orders"], order_stats["offline_paid_orders"], order_stats["online_paid_orders"],
                order_stats["gmv"] / 10000, order_stats["aov"], order_stats["refund_order_count"])
    timings["orders"] = round(time.time() - t, 2)

    # 5. 库存
    t = time.time()
    logger.info("[5/5] 模拟库存日快照与补货采购（%d 个库位 × %d SKU × %d 天）...",
                len(master["stores"]), len(master["products"]), len(config.date_list()))
    inventory_stats = inventory.generate_inventory(config, master, demand, returns, rng_inventory, writer)
    logger.info("库存完成：快照=%d, 缺货率=%.4f, 紧急补货=%d",
                inventory_stats["inventory_snapshot_rows"], inventory_stats["stockout_rate"],
                inventory_stats["emergency_replenishments"])
    timings["inventory"] = round(time.time() - t, 2)

    checks = _validate(order_df, details, refunds, order_stats)
    duration = round(time.time() - t0, 2)
    timings["total"] = duration

    manifest = {
        "project": config.project["name"],
        "brand": config.project["brand"],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
        "seed": config.seed,
        "scale": config.scale,
        "timings_sec": timings,
        "row_counts_raw": writer.table_counts,
        "dirty_injected": writer.dirty.injected,
        "online_stats": online_stats,
        "order_stats": order_stats,
        "inventory_stats": inventory_stats,
        "checks": checks,
        "daily_counts": writer.daily_counts,
    }
    manifest_path = config.path("raw") / "_manifest.json"
    write_json(manifest_path, manifest)
    logger.info("=" * 70)
    logger.info("模拟数据生成完成，用时 %.1f 秒", duration)
    logger.info("业务汇总：有效订单=%d, GMV=%.2f 万, 行为事件=%d, 库存快照=%d",
                order_stats["paid_orders"], order_stats["gmv"] / 10000,
                online_stats["behavior_events"], inventory_stats["inventory_snapshot_rows"])
    logger.info("数据清单: %s", manifest_path)
    for name, value in writer.table_counts.items():
        logger.info("  %-22s %12d 行", name, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
