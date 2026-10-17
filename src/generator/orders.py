"""交易域：线下订单、线上订单、订单行、支付、退款/退货与门店目标。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from src.common.calendar_cn import is_holiday
from . import sampling

OFFLINE_MEMBER_EXTRA = {"普通会员": 0.0, "银卡会员": 0.005, "金卡会员": 0.01, "黑卡会员": 0.02}
REFUND_REASONS = np.array(["七天无理由退货", "质量问题", "不喜欢/不合适", "发错货", "价格原因", "其他"])
REFUND_REASON_P = np.array([0.35, 0.15, 0.25, 0.10, 0.05, 0.10])
REFUND_DELAY = {
    "七天无理由退货": (0, 7), "质量问题": (0, 7), "不喜欢/不合适": (1, 14),
    "发错货": (0, 5), "价格原因": (0, 10), "其他": (0, 10),
}


def _days_in_month(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


def _primary_daily_promo(master: dict, d: date) -> tuple[dict | None, bool]:
    """返回当日主活动（不含会员日优先于会员日），以及是否会员专享。"""
    active = master["promotions_by_date"].get(d.isoformat(), [])
    if not active:
        return None, False
    campaigns = [p for p in active if int(p.get("_member_only", 0)) == 0]
    if campaigns:
        return max(campaigns, key=lambda p: float(p["discount_rate"])), False
    member_days = [p for p in active if int(p.get("_member_only", 0)) == 1]
    if member_days:
        return max(member_days, key=lambda p: float(p["discount_rate"])), True
    return None, False


def generate_offline_orders(config, master: dict, traffic: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    stores = master["store_simulation"]
    offline = stores[stores["is_offline"] == 1].reset_index(drop=True)
    store_params = {
        row["store_id"]: (row["store_type"], float(row["_base_footfall"]))
        for _, row in offline.iterrows()
    }
    traffic_map = traffic.set_index(["dt", "store_id"])["traffic_in"].to_dict()
    rows = []
    for d in config.date_list():
        dt = d.isoformat()
        promo, member_only = _primary_daily_promo(master, d)
        counts = []
        store_ids = []
        for _, store in offline.iterrows():
            sid = store["store_id"]
            tr = int(traffic_map.get((dt, sid), 0))
            if tr <= 0:
                continue
            stype = store["store_type"]
            base_conv = {"旗舰店": 0.110, "标准店": 0.125, "社区店": 0.155, "奥莱店": 0.135}[stype]
            p = base_conv * rng.uniform(0.95, 1.05)
            if d.weekday() >= 5:
                p *= 1.02
            if promo is not None:
                p *= 1.03
            n = int(rng.binomial(tr, min(p, 0.6)))
            counts.append(n)
            store_ids.extend([sid] * n)
        n_day = int(sum(counts))
        if n_day == 0:
            continue
        store_ids_arr = np.array(store_ids, dtype=object)
        members = sampling.sample_member_ids(
            rng, master["member_meta"], d, n_day,
            float(config.get("generator.offline_member_order_ratio", 0.65)),
        )
        is_member = np.array([m is not None for m in members])
        promo_ids = np.array([None] * n_day, dtype=object)
        if promo is not None:
            apply_mask = rng.random(n_day) < 0.75
            if member_only:
                apply_mask = apply_mask & is_member
            promo_ids[apply_mask] = promo["promotion_id"]
        hours = sampling.sample_store_hour(rng, n_day)
        minutes = rng.integers(0, 60, size=n_day)
        seconds = rng.integers(0, 60, size=n_day)
        order_times = [f"{dt} {int(h):02d}:{int(m):02d}:{int(s):02d}" for h, m, s in zip(hours, minutes, seconds)]
        order_ids = [f"SO{d:%Y%m%d}{i:06d}" for i in range(1, n_day + 1)]
        rows.append(pd.DataFrame({
            "order_id": order_ids,
            "order_time": order_times,
            "dt": dt,
            "store_id": store_ids_arr,
            "channel_id": "CH01",
            "member_id": members,
            "device_type": "POS",
            "online_session_id": None,
            "promotion_id": promo_ids,
            "order_status": "已完成",
            "create_time": order_times,
            "update_time": order_times,
            "_preferred_product_id": None,
            "_channel_type": "线下",
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _combine_orders(offline: pd.DataFrame, online: pd.DataFrame, master: dict) -> pd.DataFrame:
    frames = []
    if len(offline):
        frames.append(offline)
    if len(online):
        on = online.copy()
        on["_channel_type"] = "线上"
        for col in ("total_amount", "discount_amount", "shipping_fee", "payable_amount", "paid_amount"):
            if col not in on.columns:
                on[col] = 0.0
        frames.append(on)
    orders = pd.concat(frames, ignore_index=True)
    if len(orders) == 0:
        return orders
    for col, default in (
        ("online_session_id", None), ("promotion_id", None), ("_preferred_product_id", None),
        ("member_id", None), ("device_type", None),
    ):
        if col not in orders.columns:
            orders[col] = default
    orders["order_time"] = orders["order_time"].astype(str)
    orders["create_time"] = orders["create_time"].astype(str)
    orders["update_time"] = orders["update_time"].astype(str)
    orders["_order_month"] = orders["dt"].str.slice(0, 7)
    return orders.reset_index(drop=True)


def _member_level_map(master: dict) -> dict:
    return master["members"].set_index("member_id")["member_level"].to_dict()


def _promo_map(master: dict) -> dict:
    df = master["promotions"]
    return {
        row["promotion_id"]: (float(row["discount_rate"]), float(row["min_amount"]))
        for _, row in df.iterrows()
    }


def _build_lines(orders: pd.DataFrame, master: dict, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """为订单生成明细行，并返回带金额的订单头与明细。"""
    if len(orders) == 0:
        return orders, pd.DataFrame()
    products = master["products"]
    n_orders = len(orders)
    line_counts = sampling.sample_line_counts(rng, n_orders)
    order_pos = np.repeat(np.arange(n_orders), line_counts)
    lines = orders.iloc[order_pos].reset_index(drop=True)
    lines["_order_pos"] = order_pos
    lines["line_no"] = lines.groupby("_order_pos").cumcount() + 1
    lines["_month"] = pd.to_datetime(lines["dt"]).dt.month

    # 按（库位, 月）批量抽样商品，兼顾门店品类偏好与季节
    lines["_product_idx"] = -1
    for (loc, month), grp in lines.groupby(["store_id", "_month"], sort=False):
        loci = master["assortment"][loc]
        weights = master["sampling_weights"][(loc, month)]
        picks = rng.choice(loci, size=len(grp), p=weights)
        lines.loc[grp.index, "_product_idx"] = picks

    # 线上订单首行按点击偏好替换商品
    product_index = {pid: i for i, pid in enumerate(products["product_id"].to_numpy())}
    w_assort = set(master["assortment"]["W001"].tolist())
    pref_mask = (
        lines["line_no"].eq(1)
        & lines["_preferred_product_id"].notna()
        & lines["_channel_type"].eq("线上")
        & (rng.random(len(lines)) < 0.55)
    )
    for idx in lines.index[pref_mask]:
        pref = lines.at[idx, "_preferred_product_id"]
        pi = product_index.get(pref)
        if pi is not None and pi in w_assort:
            lines.at[idx, "_product_idx"] = pi

    idx_arr = lines["_product_idx"].to_numpy(dtype=int)
    product_ids = products["product_id"].to_numpy()
    top_cats = master["product_top_category"][idx_arr]
    lines["product_id"] = product_ids[idx_arr]
    lines["_top_category"] = top_cats
    lines["quantity"] = sampling.sample_quantities(rng, top_cats.tolist(), len(lines))

    list_price = master["product_price"][idx_arr]
    cost_price = master["product_cost"][idx_arr]
    lines["list_price"] = np.round(list_price, 2)
    lines["_cost_price"] = np.round(cost_price, 2)

    # 订单级折扣：活动 + 会员等级 + 随机小幅优惠
    promo_map = _promo_map(master)
    level_map = _member_level_map(master)
    lines["_member_level"] = lines["member_id"].map(level_map)
    lines["_list_amount"] = np.round(lines["list_price"] * lines["quantity"], 2)
    subtotal = lines.groupby("order_id")["_list_amount"].sum().to_dict()

    promo_arr = orders["promotion_id"].to_numpy()
    member_levels = orders["member_id"].map(level_map).to_numpy()
    rates = np.zeros(n_orders)
    for i, oid in enumerate(orders["order_id"].to_numpy()):
        promo_id = promo_arr[i]
        rate = 0.0
        if promo_id is not None and promo_id in promo_map:
            promo_rate, min_amount = promo_map[promo_id]
            if subtotal.get(oid, 0.0) >= min_amount:
                rate = promo_rate * rng.uniform(0.85, 1.10)
        extra = OFFLINE_MEMBER_EXTRA.get(member_levels[i], 0.0)
        random_discount = rng.uniform(0.0, 0.04)
        rates[i] = min(0.35, rate + extra + random_discount)
    orders = orders.copy()
    orders["_discount_rate"] = np.round(rates, 4)
    lines["_discount_rate"] = lines["_order_pos"].map(pd.Series(rates))

    sale_price = np.maximum(0.01, np.round(lines["list_price"] * (1 - lines["_discount_rate"]), 2))
    lines["sale_price"] = sale_price
    lines["line_amount"] = np.round(sale_price * lines["quantity"], 2)
    lines["discount_amount"] = np.round(lines["_list_amount"] - lines["line_amount"], 2)
    lines["cost_amount"] = np.round(lines["_cost_price"] * lines["quantity"], 2)
    lines["line_id"] = lines["order_id"] + "-" + lines["line_no"].astype(str).str.zfill(2)
    lines["update_time"] = lines["order_time"]

    # 订单头金额
    agg = lines.groupby("order_id").agg(
        agg_line_amount=("line_amount", "sum"),
        agg_list_amount=("_list_amount", "sum"),
        agg_discount_amount=("discount_amount", "sum"),
        agg_qty=("quantity", "sum"),
    ).reset_index()
    orders = orders.drop(
        columns=[c for c in ("line_amount", "list_amount", "discount_amount", "qty") if c in orders.columns]
    )
    orders = orders.merge(agg, on="order_id", how="left")
    orders[["agg_line_amount", "agg_list_amount", "agg_discount_amount", "agg_qty"]] = (
        orders[["agg_line_amount", "agg_list_amount", "agg_discount_amount", "agg_qty"]].fillna(0.0)
    )
    orders = orders.rename(columns={
        "agg_line_amount": "line_amount",
        "agg_list_amount": "list_amount",
        "agg_discount_amount": "discount_amount",
        "agg_qty": "qty",
    })
    is_online = orders["_channel_type"].eq("线上")
    orders["shipping_fee"] = np.where(is_online & (orders["line_amount"] < 99.0), 6.0, 0.0)
    orders["total_amount"] = np.round(orders["list_amount"] + orders["shipping_fee"], 2)
    orders["discount_amount"] = np.round(orders["discount_amount"], 2)
    orders["payable_amount"] = np.round(orders["line_amount"] + orders["shipping_fee"], 2)
    orders["paid_amount"] = np.where(orders["order_status"].eq("已取消"), 0.0, orders["payable_amount"])
    return orders, lines


def _add_canceled_orders(orders: pd.DataFrame, lines: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame, set[str]]:
    paid_offline = orders[(orders["_channel_type"] == "线下") & orders["order_status"].ne("已取消")]
    if len(paid_offline) == 0:
        return orders, lines, set()
    n_cancel = max(1, int(len(paid_offline) * 0.02))
    selected = paid_offline.sample(n=n_cancel, random_state=int(rng.integers(0, 2**31 - 1)))
    new_ids = ["SC" + oid[2:] for oid in selected["order_id"]]
    selected = selected.copy()
    selected["_old_order_id"] = selected["order_id"]
    selected["order_id"] = new_ids
    selected["order_status"] = "已取消"
    selected["paid_amount"] = 0.0
    id_map = dict(zip(selected["_old_order_id"], selected["order_id"]))
    canceled_lines = lines[lines["order_id"].isin(id_map)].copy()
    canceled_lines["order_id"] = canceled_lines["order_id"].map(id_map)
    canceled_lines["line_id"] = canceled_lines["order_id"] + "-" + canceled_lines["line_no"].astype(str).str.zfill(2)
    selected = selected.drop(columns=["_old_order_id"])
    orders = pd.concat([orders, selected], ignore_index=True)
    lines = pd.concat([lines, canceled_lines], ignore_index=True)
    return orders, lines, set(new_ids)


def _payment_channel(channel_id: str, n: int, rng: np.random.Generator) -> np.ndarray:
    if channel_id == "CH01":
        return rng.choice(["微信支付", "支付宝", "银联", "现金", "储值卡"], size=n, p=[0.45, 0.28, 0.15, 0.10, 0.02])
    if channel_id in ("CH02", "CH03"):
        return rng.choice(["微信支付", "支付宝", "银联", "第三方支付"], size=n, p=[0.55, 0.35, 0.07, 0.03])
    return rng.choice(["支付宝", "微信支付", "银联", "第三方支付"], size=n, p=[0.40, 0.40, 0.10, 0.10])


def _build_payments(orders: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    if len(orders) == 0:
        return pd.DataFrame()
    payments = []
    for channel in orders["channel_id"].unique():
        mask = orders["channel_id"] == channel
        subset = orders[mask]
        pay_channels = _payment_channel(channel, len(subset), rng)
        offsets = rng.integers(5, 601, size=len(subset)) if channel == "CH01" else rng.integers(0, 61, size=len(subset))
        pay_times = []
        for ot, off in zip(subset["order_time"], offsets):
            base = datetime.strptime(str(ot), "%Y-%m-%d %H:%M:%S")
            t = base + timedelta(seconds=int(off))
            if t.date() > base.date():
                t = datetime.combine(base.date(), time(23, 59, 59))
            pay_times.append(t.strftime("%Y-%m-%d %H:%M:%S"))
        is_paid = subset["order_status"].ne("已取消").to_numpy()
        payments.append(pd.DataFrame({
            "payment_id": "PAY" + subset["order_id"].astype(str),
            "order_id": subset["order_id"].to_numpy(),
            "dt": subset["dt"].to_numpy(),
            "pay_time": pay_times,
            "pay_channel": pay_channels,
            "pay_amount": np.where(is_paid, subset["paid_amount"], subset["payable_amount"]),
            "payment_status": np.where(is_paid, "成功", "失败"),
            "transaction_no": "TXN" + subset["order_id"].astype(str),
            "update_time": pay_times,
        }))
    return pd.concat(payments, ignore_index=True)


def _build_refunds(orders, lines, payments, master, config, rng) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """生成退款/退货明细；返回退款表、库存退货汇总、订单状态映射。"""
    paid_orders = orders[(orders["paid_amount"] > 0) & orders["order_status"].ne("已取消")].copy()
    if len(paid_orders) == 0:
        return pd.DataFrame(), pd.DataFrame(), {}
    # 商品品类标记（生鲜按商品保质期判断）
    prod_shelf = master["products"].set_index("product_id")["shelf_life_days"].to_dict()
    perishable_ids = {p for p, shelf in prod_shelf.items() if shelf <= 30}
    lines["_is_perishable"] = lines["product_id"].isin(perishable_ids)
    cat_flags = lines.groupby("order_id").agg(
        has_apparel=("_top_category", lambda s: int((s == "服饰鞋包").any())),
        has_digital=("_top_category", lambda s: int((s == "数码家电").any())),
        has_fresh=("_top_category", lambda s: int((s == "生鲜果蔬").any())),
        has_perishable=("_is_perishable", lambda s: int(s.any())),
    ).reset_index()
    paid_orders = paid_orders.merge(cat_flags, on="order_id", how="left")
    is_online = paid_orders["_channel_type"].eq("线上")
    base_p = np.where(is_online, 0.09, 0.03)
    base_p = base_p + 0.02 * paid_orders["has_apparel"].fillna(0).to_numpy()
    base_p = base_p + 0.015 * paid_orders["has_digital"].fillna(0).to_numpy()
    base_p = base_p + 0.01 * paid_orders["has_fresh"].fillna(0).to_numpy()
    selected = paid_orders[rng.random(len(paid_orders)) < np.minimum(base_p, 0.20)].copy()

    pay_channel_map = payments.set_index("order_id")["pay_channel"].to_dict()
    line_groups = {
        oid: grp for oid, grp in lines[lines["order_id"].isin(selected["order_id"])].groupby("order_id")
    }
    rows = []
    status_map: dict[str, str] = {}
    end_date = config.end_date
    for _, order in selected.iterrows():
        order_id = order["order_id"]
        order_dt = date.fromisoformat(order["dt"])
        reason = str(rng.choice(REFUND_REASONS, p=REFUND_REASON_P))
        lo, hi = REFUND_DELAY[reason]
        delay = int(rng.integers(lo, hi + 1))
        refund_date = order_dt + timedelta(days=delay)
        if refund_date > end_date:
            continue
        order_lines = line_groups.get(order_id)
        if order_lines is None or len(order_lines) == 0:
            continue
        full = rng.random() < 0.70
        chosen = order_lines if full else order_lines.sample(n=1, random_state=int(rng.integers(0, 2**31 - 1)))
        processing = rng.random() < 0.03
        return_allowed = (not bool(order["has_perishable"])) and (rng.random() < 0.60) and (not processing)
        refund_type = "退货退款" if return_allowed else "仅退款"
        if delay == 0:
            order_hour = int(str(order["order_time"])[11:13])
            hour = min(21, max(9, order_hour + int(rng.integers(1, 6))))
        else:
            hour = int(rng.integers(9, 22))
        refund_time = f"{refund_date.isoformat()} {hour:02d}:{int(rng.integers(0, 60)):02d}:{int(rng.integers(0, 60)):02d}"
        for _, line in chosen.iterrows():
            rows.append({
                "refund_id": f"RF{order_id}-{int(line['line_no']):02d}",
                "order_id": order_id,
                "line_id": line["line_id"],
                "dt": refund_date.isoformat(),
                "refund_time": refund_time,
                "refund_amount": round(float(line["line_amount"]), 2),
                "refund_reason": reason,
                "refund_type": refund_type,
                "refund_channel": pay_channel_map.get(order_id, "原路退回"),
                "refund_status": "处理中" if processing else "已完成",
                "return_qty": int(line["quantity"]) if return_allowed else 0,
                "update_time": refund_time,
                "product_id": line["product_id"],
                "store_id": order["store_id"],
                "_refund_date": refund_date.isoformat(),
            })
        if processing:
            status_map[order_id] = "退款中"
        elif full:
            status_map[order_id] = "已退款"
        else:
            status_map[order_id] = "部分退款"
    refunds = pd.DataFrame(rows)
    if len(refunds):
        orders.loc[orders["order_id"].isin(status_map.keys()), "order_status"] = (
            orders.loc[orders["order_id"].isin(status_map.keys()), "order_id"].map(status_map)
        )
        # 库存退货：退款日+1~3 天到仓/到店，超出窗口则不回补
        returns = refunds[(refunds["refund_status"] == "已完成") & (refunds["return_qty"] > 0)].copy()
        if len(returns):
            lag = rng.integers(1, 4, size=len(returns))
            returns["dt"] = [
                (date.fromisoformat(dt) + timedelta(days=int(l))).isoformat()
                for dt, l in zip(returns["_refund_date"], lag)
            ]
            returns = returns[returns["dt"] <= end_date.isoformat()]
            returns = returns.groupby(["dt", "store_id", "product_id"], as_index=False)["return_qty"].sum()
            returns = returns.rename(columns={"store_id": "location_id", "return_qty": "qty"})
        else:
            returns = pd.DataFrame(columns=["dt", "location_id", "product_id", "qty"])
    else:
        returns = pd.DataFrame(columns=["dt", "location_id", "product_id", "qty"])
    return refunds, returns, status_map


def _build_demand(orders: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    paid_ids = set(orders.loc[orders["paid_amount"] > 0, "order_id"])
    paid_lines = lines[lines["order_id"].isin(paid_ids)]
    demand = paid_lines.groupby(["dt", "store_id", "product_id"], as_index=False)["quantity"].sum()
    demand = demand.rename(columns={"store_id": "location_id", "quantity": "qty"})
    return demand


def _build_targets(config, orders: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    paid = orders[(orders["paid_amount"] > 0) & (orders["_channel_type"] == "线下")].copy()
    if len(paid) == 0:
        return pd.DataFrame()
    paid["target_month"] = paid["dt"].str.slice(0, 7)
    actual = paid.groupby(["store_id", "target_month"], as_index=False)["paid_amount"].sum()
    days_in_month = {}
    observed_days = {}
    for month in actual["target_month"].unique():
        year, mon = map(int, month.split("-"))
        dim = _days_in_month(year, mon)
        month_start = date(year, mon, 1)
        month_end = date(year, mon, dim)
        obs_start = max(month_start, config.start_date)
        obs_end = min(month_end, config.end_date)
        days_in_month[month] = dim
        observed_days[month] = max(1, (obs_end - obs_start).days + 1)
    actual["days_in_month"] = actual["target_month"].map(days_in_month)
    actual["observed_days"] = actual["target_month"].map(observed_days)
    actual["factor"] = rng.uniform(0.92, 1.10, size=len(actual))
    # 月度目标按全月口径：用数据窗口内日均销售外推到整月，避免部分月份达成绩效失真
    actual["target_amount"] = (
        actual["paid_amount"] / actual["observed_days"] * actual["days_in_month"] * actual["factor"] / 100
    ).round() * 100
    actual["target_amount"] = actual["target_amount"].clip(lower=1000)
    actual["target_id"] = "T" + actual["store_id"] + actual["target_month"].str.replace("-", "")
    actual["update_time"] = actual["target_month"] + "-01 00:00:00"
    return actual[["target_id", "store_id", "target_month", "target_amount", "update_time"]]


def generate_orders(config, master: dict, traffic: pd.DataFrame, online_orders: pd.DataFrame, rng: np.random.Generator):
    offline = generate_offline_orders(config, master, traffic, rng)
    orders = _combine_orders(offline, online_orders, master)
    orders, lines = _build_lines(orders, master, rng)
    orders, lines, canceled_ids = _add_canceled_orders(orders, lines, rng)
    payments = _build_payments(orders, rng)
    refunds, returns, _ = _build_refunds(orders, lines, payments, master, config, rng)
    demand = _build_demand(orders, lines)
    targets = _build_targets(config, orders, rng)

    # 清理内部字段，保留写入所需字段
    detail_cols = ["order_id", "line_id", "product_id", "quantity", "list_price", "sale_price",
                   "discount_amount", "line_amount", "cost_amount", "dt", "update_time"]
    details = lines[detail_cols].copy()
    order_cols = ["order_id", "order_time", "dt", "store_id", "channel_id", "member_id", "device_type",
                  "online_session_id", "promotion_id", "order_status", "total_amount", "discount_amount",
                  "shipping_fee", "payable_amount", "paid_amount", "create_time", "update_time"]
    orders_out = orders[order_cols].copy()
    refund_cols = ["refund_id", "order_id", "line_id", "dt", "refund_time", "refund_amount",
                   "refund_reason", "refund_type", "refund_channel", "refund_status", "return_qty", "update_time"]
    refunds_out = refunds[refund_cols].copy() if len(refunds) else pd.DataFrame(columns=refund_cols)
    payment_cols = ["payment_id", "order_id", "dt", "pay_time", "pay_channel", "pay_amount",
                    "payment_status", "transaction_no", "update_time"]
    payments_out = payments[payment_cols].copy()

    paid = orders_out[orders_out["paid_amount"] > 0]
    stats = {
        "paid_orders": int(len(paid)),
        "offline_paid_orders": int(len(paid[paid["channel_id"] == "CH01"])),
        "online_paid_orders": int(len(paid[paid["channel_id"] != "CH01"])),
        "canceled_orders": int(len(orders_out) - len(paid)),
        "gmv": round(float(paid["paid_amount"].sum()), 2),
        "aov": round(float(paid["paid_amount"].mean()), 2) if len(paid) else 0.0,
        "order_lines": int(len(details)),
        "units": int(details["quantity"].sum()),
        "refund_order_count": int(refunds_out["order_id"].nunique()) if len(refunds_out) else 0,
        "refund_amount": round(float(refunds_out.loc[refunds_out["refund_status"] == "已完成", "refund_amount"].sum()), 2),
        "member_gmv_ratio": round(float(paid.loc[paid["member_id"].notna(), "paid_amount"].sum() / max(paid["paid_amount"].sum(), 1)), 4),
    }
    return orders_out, details, payments_out, refunds_out, demand, returns, targets, stats, canceled_ids
