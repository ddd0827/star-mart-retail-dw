"""验收脚本：检查 ADS、对账结果、质量报告与看板产物。

用法：
    .venv\\Scripts\\python.exe scripts\\verify_outputs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
ADS_TABLES = [
    "ads_operation_overview", "ads_store_performance", "ads_category_structure",
    "ads_product_topn", "ads_member_rfm", "ads_member_retention",
    "ads_member_repurchase", "ads_inventory_turnover", "ads_online_funnel",
    "ads_promotion_effect",
]


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def main() -> int:
    export_dir = ROOT / "output" / "ads_export"
    missing = []
    for table in ADS_TABLES:
        for ext in ("csv", "json"):
            path = export_dir / f"{table}.{ext}"
            if not path.exists():
                missing.append(str(path))
    if missing:
        fail("缺少 ADS 导出文件:\n" + "\n".join(missing))
    print(f"[PASS] 10 张 ADS 表 CSV/JSON 均已导出")

    manifest_path = ROOT / "output" / "run_log" / "generation_manifest.json"
    if not manifest_path.exists():
        fail("缺少生成清单 generation_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stats = manifest["order_stats"]

    overview = pd.read_csv(export_dir / "ads_operation_overview.csv", encoding="utf-8-sig")
    gmv = float(overview["gmv"].sum())
    orders = int(overview["order_cnt"].sum())
    if abs(gmv - float(stats["gmv"])) > 0.05:
        fail(f"ADS GMV 与生成清单不一致: {gmv} vs {stats['gmv']}")
    if orders != int(stats["paid_orders"]):
        fail(f"ADS 订单量与生成清单不一致: {orders} vs {stats['paid_orders']}")
    print(f"[PASS] ADS 对账：GMV={gmv:,.2f}, 有效订单={orders:,}")

    dq_path = ROOT / "output" / "quality" / "dq_report_latest.csv"
    if not dq_path.exists():
        fail("缺少质量报告 dq_report_latest.csv")
    dq = pd.read_csv(dq_path)
    failures = dq[(dq["severity"] == "critical") & (dq["status"] != "PASS")]
    if len(failures):
        fail("质量报告存在 critical 失败:\n" + failures.to_string())
    print(f"[PASS] 质量报告：{len(dq)} 条规则全部通过")

    daily_dq = ROOT / "output" / "quality" / "dq_report_latest_daily.csv"
    if daily_dq.exists():
        daily = pd.read_csv(daily_dq)
        daily_failures = daily[(daily["severity"] == "critical") & (daily["status"] != "PASS")]
        if len(daily_failures):
            fail("日增量质量报告存在 critical 失败")
        print(f"[PASS] 日增量质量报告：{len(daily)} 条规则全部通过")

    for path in (
        ROOT / "output" / "dashboard.html",
        ROOT / "output" / "dashboard_assets" / "echarts.min.js",
        ROOT / "output" / "dashboard_preview.png",
    ):
        if not path.exists():
            fail(f"缺少看板产物: {path}")
    print("[PASS] 看板 HTML、本地 ECharts 与预览图均存在")

    powerbi_dir = ROOT / "output" / "powerbi"
    for path in (
        powerbi_dir / "data" / "dim_date.csv",
        powerbi_dir / "data" / "fact_operation_day.csv",
        powerbi_dir / "data" / "fact_member_rfm.csv",
        powerbi_dir / "theme" / "star_mart_theme.json",
        powerbi_dir / "measures.dax",
        powerbi_dir / "_manifest.json",
    ):
        if not path.exists():
            fail(f"缺少 Power BI 产物: {path}")
    pb_manifest = json.loads((powerbi_dir / "_manifest.json").read_text(encoding="utf-8"))
    if len(pb_manifest.get("row_counts", {})) != 17:
        fail(f"Power BI 数据集表数量异常: {len(pb_manifest.get('row_counts', {}))}，期望 17")
    print(f"[PASS] Power BI 数据集：{len(pb_manifest['row_counts'])} 张表、"
          f"{len(pb_manifest.get('relationships', []))} 条关系、主题与 DAX 度量齐全")

    print("-" * 60)
    print("验收通过：数据链路、对账、质量与展示产物完整。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
