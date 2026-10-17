"""生成离线可打开的静态经营看板（ECharts + 内嵌数据）。"""
from __future__ import annotations

import html
import json
import math
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.common.config import Config
from src.common.logger import get_logger

SEGMENT_ORDER = [
    "重要价值客户", "重要保持客户", "重要发展客户", "重要挽留客户",
    "一般价值客户", "一般保持客户", "一般发展客户", "一般挽留客户",
]


def _read_csv(config: Config, name: str) -> pd.DataFrame:
    path = config.path("ads_export") / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    if "dt" in df.columns:
        df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
    return df


def _num(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def _fmt_int(v) -> str:
    try:
        return f"{int(round(float(v))):,}"
    except Exception:
        return "—"


def _fmt_money(v, unit: bool = True) -> str:
    try:
        v = float(v)
    except Exception:
        return "—"
    prefix = "¥" if unit else ""
    if abs(v) >= 1e8:
        return f"{prefix}{v / 1e8:,.2f}亿"
    if abs(v) >= 1e4:
        return f"{prefix}{v / 1e4:,.1f}万"
    return f"{prefix}{v:,.0f}"


def _fmt_pct(v, digits: int = 1, signed: bool = False) -> str:
    try:
        v = float(v)
    except Exception:
        return "—"
    if math.isnan(v):
        return "—"
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v * 100:,.{digits}f}%"


def _fmt_pp(v) -> str:
    try:
        v = float(v)
    except Exception:
        return "—"
    return f"{v * 100:+.2f}pp"


def _delta(cur, prev, points: bool = False):
    try:
        cur, prev = float(cur), float(prev)
        if prev == 0:
            return None
        return (cur - prev) / prev if not points else (cur - prev)
    except Exception:
        return None


def _delta_html(value, good_when_up: bool = True, points: bool = False) -> tuple[str, str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—", "neutral"
    cls = "up" if value > 0 else ("down" if value < 0 else "neutral")
    if value != 0:
        good = (value > 0) == good_when_up
        cls = "good" if good else "bad"
    arrow = "▲" if value > 0 else ("▼" if value < 0 else "•")
    text = _fmt_pp(value) if points else _fmt_pct(value, 1, signed=True)
    return f"{arrow} {text}", cls


def _table(headers: list[str], rows: list[list[str]]) -> dict:
    return {"headers": headers, "rows": rows}


def _dominant_completion(store_df: pd.DataFrame) -> dict:
    if store_df.empty:
        return {}
    latest = store_df.sort_values("dt").groupby("store_name", as_index=False).tail(1)
    return dict(zip(latest["store_name"], latest.get("mtd_completion_rate", pd.Series(dtype=float))))


def _build_data(config: Config) -> dict:
    overview = _read_csv(config, "ads_operation_overview")
    store = _read_csv(config, "ads_store_performance")
    category = _read_csv(config, "ads_category_structure")
    inventory = _read_csv(config, "ads_inventory_turnover")
    funnel = _read_csv(config, "ads_online_funnel")
    rfm = _read_csv(config, "ads_member_rfm")
    promotion = _read_csv(config, "ads_promotion_effect")

    overview = _num(overview, ["gmv", "online_gmv", "order_cnt", "member_gmv", "refund_amount", "refund_order_cnt", "active_member_cnt", "new_member_cnt", "net_sales_amount"])
    store = _num(store, ["gmv", "order_cnt", "avg_order_value", "mtd_gmv", "mtd_target"])
    if "mtd_completion_rate" in store.columns:
        store["mtd_completion_rate"] = pd.to_numeric(store["mtd_completion_rate"], errors="coerce")
    category = _num(category, ["sales_amount", "sale_qty", "sales_share", "refund_rate", "gross_margin_rate"])
    inventory = _num(inventory, ["ending_stock_value", "avg_stock_value_30d"])
    for col in ("turnover_days", "stockout_rate_30d", "sell_through_rate_30d"):
        if col in inventory.columns:
            inventory[col] = pd.to_numeric(inventory[col], errors="coerce")
    funnel = _num(funnel, ["visit_sessions", "browse_sessions", "cart_sessions", "checkout_sessions", "pay_sessions", "visit_to_pay_rate", "online_gmv", "online_order_cnt"])
    rfm = _num(rfm, ["monetary", "frequency", "recency_days"])
    promotion = _num(promotion, ["activity_avg_gmv", "baseline_avg_gmv", "gmv_lift_rate", "incremental_gmv", "promo_discount", "promotion_roi", "incremental_gross_profit"])

    if overview.empty:
        raise RuntimeError("ADS 经营总览为空，无法生成看板；请先运行数仓调度")

    latest = overview["dt"].max().date()
    data_start = overview["dt"].min().date()
    win_start = latest - timedelta(days=29)
    prev_end = win_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=29)

    cur = overview[(overview["dt"] >= pd.Timestamp(win_start)) & (overview["dt"] <= pd.Timestamp(latest))]
    prev = overview[(overview["dt"] >= pd.Timestamp(prev_start)) & (overview["dt"] <= pd.Timestamp(prev_end))]

    def sums(df):
        out = {c: float(df[c].sum()) if c in df.columns else 0.0 for c in (
            "gmv", "online_gmv", "order_cnt", "refund_amount", "refund_order_cnt", "active_member_cnt", "new_member_cnt")}
        out["member_gmv"] = float((df["gmv"] * df["member_gmv_ratio"]).sum()) if {"gmv", "member_gmv_ratio"}.issubset(df.columns) else 0.0
        return out

    cs, ps = sums(cur), sums(prev)

    # ---------------- Hero & KPI ----------------
    gmv_30 = cs["gmv"]
    gmv_prev = ps["gmv"]
    orders_30 = cs["order_cnt"]
    aov_30 = gmv_30 / orders_30 if orders_30 else 0
    aov_prev = ps["gmv"] / ps["order_cnt"] if ps["order_cnt"] else 0
    member_ratio = cs["member_gmv"] / gmv_30 if gmv_30 else 0
    member_ratio_prev = ps["member_gmv"] / ps["gmv"] if ps["gmv"] else 0
    online_ratio = cs["online_gmv"] / gmv_30 if gmv_30 else 0
    online_ratio_prev = ps["online_gmv"] / ps["gmv"] if ps["gmv"] else 0
    refund_rate = cs["refund_amount"] / gmv_30 if gmv_30 else 0
    refund_rate_prev = ps["refund_amount"] / ps["gmv"] if ps["gmv"] else 0

    inv_latest = inventory[(inventory["dt"] == pd.Timestamp(latest)) & (inventory["is_offline"] == 1)] if not inventory.empty else pd.DataFrame()
    inv_valid = inv_latest.dropna(subset=["turnover_days"]) if not inv_latest.empty else pd.DataFrame()
    avg_turnover = float(inv_valid["turnover_days"].mean()) if not inv_valid.empty else None

    hero_delta, hero_cls = _delta_html(_delta(gmv_30, gmv_prev), good_when_up=True)
    kpis = [
        {"label": "近30天订单量", "value": _fmt_int(orders_30), "delta": _delta_html(_delta(orders_30, ps["order_cnt"]), True)[0],
         "delta_cls": _delta_html(_delta(orders_30, ps["order_cnt"]), True)[1], "note": "有效支付订单"},
        {"label": "客单价", "value": f"¥{aov_30:,.2f}", "delta": _delta_html(_delta(aov_30, aov_prev), True)[0],
         "delta_cls": _delta_html(_delta(aov_30, aov_prev), True)[1], "note": "GMV / 有效订单"},
        {"label": "会员销售占比", "value": _fmt_pct(member_ratio), "delta": _delta_html(_delta(member_ratio, member_ratio_prev, points=True), True, points=True)[0],
         "delta_cls": _delta_html(_delta(member_ratio, member_ratio_prev, points=True), True, points=True)[1], "note": "会员 GMV / 总 GMV"},
        {"label": "线上销售占比", "value": _fmt_pct(online_ratio), "delta": _delta_html(_delta(online_ratio, online_ratio_prev, points=True), True, points=True)[0],
         "delta_cls": "neutral", "note": "线上 GMV / 总 GMV"},
        {"label": "退款率", "value": _fmt_pct(refund_rate), "delta": _delta_html(_delta(refund_rate, refund_rate_prev, points=True), False, points=True)[0],
         "delta_cls": _delta_html(_delta(refund_rate, refund_rate_prev, points=True), False, points=True)[1], "note": "退款额 / GMV"},
        {"label": "平均库存周转", "value": f"{avg_turnover:,.1f} 天" if avg_turnover is not None else "—",
         "delta": "—", "delta_cls": "neutral", "note": "近30日，线下门店均值"},
    ]

    # ---------------- Trend ----------------
    trend_df = overview.sort_values("dt").tail(90)
    trend = {
        "labels": [d.strftime("%m-%d") for d in trend_df["dt"]],
        "gmv": [round(float(v), 2) for v in trend_df["gmv"]],
        "orders": [int(v) for v in trend_df["order_cnt"]],
    }
    trend_table = _table(["日期", "GMV", "订单量", "退款率"], [
        [d.strftime("%Y-%m-%d"), _fmt_money(g), _fmt_int(o), _fmt_pct(r)]
        for d, g, o, r in zip(trend_df["dt"], trend_df["gmv"], trend_df["order_cnt"], trend_df["refund_rate"])
    ])

    # ---------------- Channel（按月，线下/线上堆叠） ----------------
    ov = overview.copy()
    ov["month"] = ov["dt"].dt.strftime("%Y-%m")
    monthly = ov.groupby("month", as_index=False).agg(gmv=("gmv", "sum"), online_gmv=("online_gmv", "sum"))
    monthly["offline_gmv"] = monthly["gmv"] - monthly["online_gmv"]
    monthly = monthly.tail(6)
    channel = {
        "labels": monthly["month"].tolist(),
        "offline": [round(float(v), 2) for v in monthly["offline_gmv"]],
        "online": [round(float(v), 2) for v in monthly["online_gmv"]],
    }
    channel_table = _table(["月份", "线下 GMV", "线上 GMV", "线上占比"], [
        [m, _fmt_money(off), _fmt_money(on), _fmt_pct(on / (off + on) if (off + on) else 0)]
        for m, off, on in zip(monthly["month"], monthly["offline_gmv"], monthly["online_gmv"])
    ])

    # ---------------- Category（近30天） ----------------
    cat = category[category["dt"] >= pd.Timestamp(win_start)] if not category.empty else category
    cat_agg = cat.groupby("top_category_name", as_index=False).agg(sales_amount=("sales_amount", "sum"), sale_qty=("sale_qty", "sum"))
    cat_agg = cat_agg.sort_values("sales_amount", ascending=False)
    total_cat = cat_agg["sales_amount"].sum()
    category_data = {
        "labels": cat_agg["top_category_name"].tolist(),
        "values": [round(float(v), 2) for v in cat_agg["sales_amount"]],
        "shares": [round(float(v) / total_cat, 4) if total_cat else 0 for v in cat_agg["sales_amount"]],
    }
    category_table = _table(["一级品类", "销售额", "销量", "销售占比"], [
        [name, _fmt_money(v), _fmt_int(q), _fmt_pct(s)]
        for name, v, q, s in zip(cat_agg["top_category_name"], cat_agg["sales_amount"], cat_agg["sale_qty"], category_data["shares"])
    ])

    # ---------------- Store（近30天 + 最新月累计达成） ----------------
    store30 = store[store["dt"] >= pd.Timestamp(win_start)] if not store.empty else store
    store_agg = store30.groupby(["store_name", "store_type"], as_index=False).agg(gmv=("gmv", "sum"), order_cnt=("order_cnt", "sum"))
    completion = _dominant_completion(store)
    store_agg["completion"] = store_agg["store_name"].map(completion)
    store_agg = store_agg.sort_values("gmv", ascending=False).head(10)
    store_data = {
        "labels": store_agg["store_name"].tolist(),
        "values": [round(float(v), 2) for v in store_agg["gmv"]],
        "completion": [None if pd.isna(v) else round(float(v), 4) for v in store_agg["completion"]],
    }
    store_table = _table(["排名", "门店", "店型", "近30天 GMV", "订单量", "MTD 目标达成"], [
        [str(i), name, stype, _fmt_money(g), _fmt_int(o), _fmt_pct(c) if c is not None and not pd.isna(c) else "—"]
        for i, (name, stype, g, o, c) in enumerate(zip(store_agg["store_name"], store_agg["store_type"], store_agg["gmv"], store_agg["order_cnt"], store_agg["completion"]), 1)
    ])

    # ---------------- Funnel（近30天） ----------------
    f = funnel[funnel["dt"] >= pd.Timestamp(win_start)] if not funnel.empty else funnel
    stage_keys = ["visit_sessions", "browse_sessions", "cart_sessions", "checkout_sessions", "pay_sessions"]
    stage_names = ["访问", "浏览商品", "加入购物车", "进入结算", "支付成功"]
    stage_values = [int(f[k].sum()) if k in f.columns else 0 for k in stage_keys]
    funnel_data = {"labels": stage_names, "values": stage_values}
    funnel_rows = []
    for i, (name, value) in enumerate(zip(stage_names, stage_values)):
        prev_v = stage_values[i - 1] if i > 0 else None
        funnel_rows.append([
            name, _fmt_int(value),
            _fmt_pct(value / prev_v) if prev_v else "—",
            _fmt_pct(value / stage_values[0]) if stage_values[0] else "—",
        ])
    funnel_table = _table(["阶段", "会话数", "较上一阶段", "较访问"], funnel_rows)

    # ---------------- RFM ----------------
    rfm_latest = rfm[rfm["dt"] == pd.Timestamp(latest)] if not rfm.empty else rfm
    if not rfm_latest.empty:
        rfm_agg = rfm_latest.groupby("rfm_segment", as_index=False).agg(count=("member_id", "count"), monetary=("monetary", "sum"))
        rfm_agg["segment"] = pd.Categorical(rfm_agg["rfm_segment"], categories=SEGMENT_ORDER, ordered=True)
        rfm_agg = rfm_agg.sort_values("segment")
        total_members = rfm_agg["count"].sum()
        rfm_data = {
            "labels": rfm_agg["rfm_segment"].tolist(),
            "counts": [int(v) for v in rfm_agg["count"]],
            "monetary": [round(float(v), 2) for v in rfm_agg["monetary"]],
        }
        rfm_table = _table(["客群", "会员数", "占比", "累计净消费"], [
            [seg, _fmt_int(c), _fmt_pct(c / total_members if total_members else 0), _fmt_money(m)]
            for seg, c, m in zip(rfm_agg["rfm_segment"], rfm_agg["count"], rfm_agg["monetary"])
        ])
    else:
        rfm_data = {"labels": [], "counts": [], "monetary": []}
        rfm_table = _table(["客群", "会员数", "占比", "累计净消费"], [])

    # ---------------- Inventory（最新日，线下门店） ----------------
    inv_day = inventory[inventory["dt"] == pd.Timestamp(latest)] if not inventory.empty else inventory
    inv_day = inv_day[inv_day["is_offline"] == 1] if not inv_day.empty else inv_day
    inv_day = inv_day.dropna(subset=["turnover_days"]) if not inv_day.empty else inv_day
    inv_day = inv_day.sort_values("turnover_days", ascending=False).head(10) if not inv_day.empty else inv_day
    inventory_data = {
        "labels": inv_day["location_name"].tolist() if not inv_day.empty else [],
        "values": [round(float(v), 2) for v in inv_day["turnover_days"]] if not inv_day.empty else [],
    }
    inventory_table = _table(["门店", "周转天数", "缺货率", "售罄率", "期末库存金额"], [
        [name, f"{v:,.1f} 天", _fmt_pct(s), _fmt_pct(st), _fmt_money(val)]
        for name, v, s, st, val in zip(inv_day["location_name"], inv_day["turnover_days"], inv_day["stockout_rate_30d"], inv_day["sell_through_rate_30d"], inv_day["ending_stock_value"])
    ]) if not inv_day.empty else _table(["门店", "周转天数", "缺货率", "售罄率", "期末库存金额"], [])

    # ---------------- Promotion ----------------
    promo_latest = promotion[promotion["dt"] == pd.Timestamp(latest)] if not promotion.empty else promotion
    promo_latest = promo_latest.sort_values("incremental_gmv", ascending=False).head(10) if not promo_latest.empty else promo_latest
    promo_data = {
        "labels": (promo_latest["promotion_name"] + " · " + promo_latest["channel_name"]).tolist() if not promo_latest.empty else [],
        "values": [round(float(v), 2) for v in promo_latest["incremental_gmv"]] if not promo_latest.empty else [],
    }
    promo_table = _table(["活动", "渠道", "活动日均 GMV", "基线日均 GMV", "提升率", "增量 GMV", "让利额", "ROI"], [
        [name, ch, _fmt_money(a), _fmt_money(b), _fmt_pct(lift, 1, signed=True), _fmt_money(inc), _fmt_money(disc), f"{roi:,.2f}" if not pd.isna(roi) else "—"]
        for name, ch, a, b, lift, inc, disc, roi in zip(
            promo_latest["promotion_name"], promo_latest["channel_name"], promo_latest["activity_avg_gmv"],
            promo_latest["baseline_avg_gmv"], promo_latest["gmv_lift_rate"], promo_latest["incremental_gmv"],
            promo_latest["promo_discount"], promo_latest["promotion_roi"])
    ]) if not promo_latest.empty else _table(["活动", "渠道", "活动日均 GMV", "基线日均 GMV", "提升率", "增量 GMV", "让利额", "ROI"], [])

    # ---------------- charts / data payload ----------------
    charts = {
        "trend": trend,
        "channel": channel,
        "category": category_data,
        "store": store_data,
        "funnel": funnel_data,
        "rfm": rfm_data,
        "inventory": inventory_data,
        "promotion": promo_data,
    }

    return {
        "brand": config.project.get("brand", "星选生活"),
        "project": config.project.get("name", ""),
        "latest": latest.isoformat(),
        "data_start": data_start.isoformat(),
        "data_end": latest.isoformat(),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hero": {
            "label": "近30天销售额",
            "value": _fmt_money(gmv_30),
            "delta": hero_delta,
            "delta_cls": hero_cls,
            "note": f"{win_start.isoformat()} 至 {latest.isoformat()} · 较前30天",
        },
        "kpis": kpis,
        "charts": charts,
        "tables": {
            "trend": trend_table,
            "channel": channel_table,
            "category": category_table,
            "store": store_table,
            "funnel": funnel_table,
            "rfm": rfm_table,
            "inventory": inventory_table,
            "promotion": promo_table,
        },
        "summary": {
            "orders_30d": _fmt_int(orders_30),
            "members_30d": _fmt_int(cs["active_member_cnt"] / max(len(cur), 1)),
            "new_members_30d": _fmt_int(cs["new_member_cnt"]),
            "online_gmv_30d": _fmt_money(cs["online_gmv"]),
        },
    }


def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def build_dashboard(config: Config) -> Path:
    logger = get_logger()
    payload = _build_data(config)
    env = Environment(
        loader=FileSystemLoader(str(config.root / "src" / "report" / "templates")),
        autoescape=True,
    )
    template = env.get_template("dashboard.html.j2")
    out_html = config.path("output") / "dashboard.html"
    assets_dir = config.path("dashboard_assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config.root / "src" / "report" / "assets" / "echarts.min.js", assets_dir / "echarts.min.js")
    html_text = template.render(
        p=payload,
        data_json=json.dumps(_json_safe(payload["charts"]), ensure_ascii=False),
        generated_at=payload["generated_at"],
    )
    out_html.write_text(html_text, encoding="utf-8")
    logger.info("看板已生成: %s", out_html)
    return out_html
