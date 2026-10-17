"""线上渠道：会话、行为漏斗、线上订单种子。"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import sampling

ONLINE_WEEKDAY_FACTOR = np.array([0.92, 0.92, 0.95, 0.97, 1.05, 1.22, 1.12])
HOLIDAY_ONLINE_FACTOR = {
    "劳动节": 1.15, "端午节": 1.10, "中秋节": 1.18, "国庆节": 1.28,
}
CAMPAIGN_ONLINE_FACTOR = {
    "五一欢乐购": 1.18, "618年中大促": 1.45, "端午安康": 1.12,
    "中秋团圆节": 1.18, "国庆黄金周": 1.30,
}
CAMPAIGN_APPLY_PROB = {
    "五一欢乐购": 0.82, "618年中大促": 0.88, "端午安康": 0.78,
    "中秋团圆节": 0.80, "国庆黄金周": 0.84, "会员日": 0.65,
}
CHANNEL_CHOICES = np.array(["CH02", "CH03", "CH04"])
CHANNEL_PROBS = np.array([0.45, 0.30, 0.25])
ENTRY_PAGES = np.array(["首页", "品类页", "商品详情页", "活动页", "搜索结果页"])
ENTRY_PROBS = np.array([0.42, 0.20, 0.25, 0.06, 0.07])


def _fmt_sec(sec: np.ndarray | int) -> str | list[str]:
    def one(s: int) -> str:
        s = int(min(max(s, 0), 86399))
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    if np.isscalar(sec):
        return one(int(sec))
    return [one(int(x)) for x in sec]


def _device_by_channel(rng: np.random.Generator, channels: np.ndarray) -> np.ndarray:
    devices = np.empty(len(channels), dtype=object)
    for ch, probs in (
        ("CH02", [0.38, 0.52, 0.10]),
        ("CH03", [0.40, 0.55, 0.05]),
        ("CH04", [0.05, 0.20, 0.75]),
    ):
        mask = channels == ch
        if mask.any():
            devices[mask] = rng.choice(["iOS", "Android", "H5"], size=int(mask.sum()), p=probs)
    return devices


def _session_count(config, master: dict, d: date, progress: float, rng: np.random.Generator) -> int:
    base = int(config.scale["online_sessions_per_day"])
    factor = ONLINE_WEEKDAY_FACTOR[d.weekday()]
    from src.common.calendar_cn import holiday_name

    hn = holiday_name(d)
    if hn:
        factor *= HOLIDAY_ONLINE_FACTOR.get(hn, 1.10)
    promo_list = master["promotions_by_date"].get(d.isoformat(), [])
    promo_factor = 1.0
    for p in promo_list:
        if int(p.get("_member_only", 0)) == 1:
            promo_factor = max(promo_factor, 1.06)
        else:
            promo_factor = max(promo_factor, CAMPAIGN_ONLINE_FACTOR.get(p["promotion_name"], 1.1))
    factor *= promo_factor
    factor *= 0.94 + 0.14 * progress
    factor *= rng.uniform(0.94, 1.06)
    return max(100, int(round(base * factor)))


def _primary_promo(master: dict, d: date, member_ids: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, dict | None]:
    active = master["promotions_by_date"].get(d.isoformat(), [])
    if not active:
        return np.array([None] * len(member_ids), dtype=object), None
    campaigns = [p for p in active if int(p.get("_member_only", 0)) == 0]
    member_days = [p for p in active if int(p.get("_member_only", 0)) == 1]
    primary = max(campaigns, key=lambda p: float(p["discount_rate"])) if campaigns else (
        max(member_days, key=lambda p: float(p["discount_rate"])) if member_days else None
    )
    if primary is None:
        return np.array([None] * len(member_ids), dtype=object), None
    promo_ids = np.array([None] * len(member_ids), dtype=object)
    is_member = np.array([m is not None for m in member_ids])
    if int(primary.get("_member_only", 0)) == 1:
        ratio = CAMPAIGN_APPLY_PROB["会员日"]
        mask = is_member & (rng.random(len(member_ids)) < ratio)
    else:
        ratio = CAMPAIGN_APPLY_PROB.get(primary["promotion_name"], 0.8)
        mask = rng.random(len(member_ids)) < ratio
    promo_ids[mask] = primary["promotion_id"]
    return promo_ids, primary


def generate_online(
    config,
    master: dict,
    rng: np.random.Generator,
    writer,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    products = master["products"]
    product_ids = products["product_id"].to_numpy()
    dates = config.date_list()
    n_days = len(dates)
    online_orders: list[pd.DataFrame] = []
    daily_counts: dict[str, dict[str, int]] = {}
    keywords = np.array(list(master["sub_to_top"].keys()) + ["坚果", "牛奶", "纸巾", "洗衣液", "运动鞋", "耳机", "礼盒", "零食"])
    www = "W001"

    for day_idx, d in enumerate(dates):
        progress = day_idx / max(1, n_days - 1)
        n_sessions = _session_count(config, master, d, progress, rng)
        sid = np.array([f"SE{d:%Y%m%d}{i:07d}" for i in range(1, n_sessions + 1)])
        channels = rng.choice(CHANNEL_CHOICES, size=n_sessions, p=CHANNEL_PROBS)
        devices = _device_by_channel(rng, channels)
        member_ids = sampling.sample_member_ids(
            rng, master["member_meta"], d, n_sessions,
            float(config.get("generator.online_member_session_ratio", 0.65)),
        )
        is_member = np.array([m is not None for m in member_ids])
        user_type = np.where(is_member, "会员", "游客")
        visitors = np.array([f"V{d:%Y%m%d}{i:07d}" for i in range(1, n_sessions + 1)], dtype=object)
        promo_ids, primary_promo = _primary_promo(master, d, member_ids, rng)
        entry_pages = rng.choice(ENTRY_PAGES, size=n_sessions, p=ENTRY_PROBS)

        # 漏斗标记：保证访问 >= 浏览 >= 加购 >= 结算 >= 支付
        promo_uplift = 1.0 if primary_promo is None else 1.08
        browse = rng.random(n_sessions) < min(0.62, 0.55 * promo_uplift)
        search = rng.random(n_sessions) < 0.30
        cart = rng.random(n_sessions) < min(0.24, 0.20 * promo_uplift)
        browse = browse | cart
        checkout = cart & (rng.random(n_sessions) < 0.52)
        pay_rate = min(0.86, 0.77 * promo_uplift)
        paid = checkout & (rng.random(n_sessions) < pay_rate)
        # 更严格的漏斗：结算必须加购，支付必须结算
        checkout = checkout & cart
        paid = paid & checkout

        # 会话开始时间
        hours = sampling.sample_online_hour(rng, n_sessions)
        start_sec = hours * 3600 + rng.integers(0, 3600, size=n_sessions)
        start_sec = np.minimum(start_sec, 82799)  # 22:59:59 前开始
        pay_sec = np.where(paid, np.minimum(start_sec + rng.integers(300, 1800, size=n_sessions), 86399), -1)
        end_sec = np.where(paid, pay_sec, np.minimum(start_sec + rng.integers(600, 3600, size=n_sessions), 86399))

        # 分配线上订单号
        order_ids = np.array([None] * n_sessions, dtype=object)
        paid_pos = np.flatnonzero(paid)
        for seq, pos in enumerate(paid_pos, start=1):
            order_ids[pos] = f"ON{d:%Y%m%d}{seq:06d}"

        # 浏览会话的商品曝光
        browse_pos = np.flatnonzero(browse)
        exp_counts = rng.integers(3, 9, size=len(browse_pos))
        rep_pos = np.repeat(browse_pos, exp_counts)
        loci = master["assortment"][www]
        weights = master["sampling_weights"][(www, d.month)]
        exp_picks = rng.choice(loci, size=len(rep_pos), p=weights)
        exp_products = product_ids[exp_picks]
        exp_sec = np.minimum(start_sec[rep_pos] + rng.integers(20, 900, size=len(rep_pos)), 86399)
        click_offsets = np.concatenate([[0], np.cumsum(exp_counts)[:-1]]) if len(exp_counts) else np.array([], dtype=int)
        click_products = exp_products[click_offsets] if len(exp_counts) else np.array([], dtype=object)
        click_sec = np.minimum(exp_sec[click_offsets] + rng.integers(5, 120, size=len(click_offsets)), 86399) if len(exp_counts) else np.array([], dtype=int)
        click_map = {int(pos): prod for pos, prod in zip(browse_pos, click_products)}

        cart_pos = np.flatnonzero(cart)
        cart_products = []
        for pos in cart_pos:
            cart_products.append(click_map.get(int(pos)) or product_ids[int(rng.choice(loci, p=weights))])
        cart_products = np.array(cart_products, dtype=object)
        checkout_pos = np.flatnonzero(checkout)
        pay_pos = np.flatnonzero(paid)

        # 组装事件
        event_frames = []
        base = pd.DataFrame({
            "session_id": sid, "dt": d.isoformat(), "event_time": [f"{d} {t}" for t in _fmt_sec(start_sec)],
            "member_id": member_ids, "user_type": user_type, "channel_id": channels, "device_type": devices,
            "event_type": "页面浏览", "page_type": entry_pages, "product_id": None,
            "search_keyword": None, "order_id": None, "promotion_id": promo_ids,
        })
        event_frames.append(base)
        if search.any():
            sp = np.flatnonzero(search)
            event_frames.append(pd.DataFrame({
                "session_id": sid[sp], "dt": d.isoformat(),
                "event_time": [f"{d} {t}" for t in _fmt_sec(np.minimum(start_sec[sp] + rng.integers(3, 120, size=len(sp)), 86399))],
                "member_id": member_ids[sp], "user_type": user_type[sp], "channel_id": channels[sp],
                "device_type": devices[sp], "event_type": "搜索", "page_type": "搜索结果页",
                "product_id": None, "search_keyword": rng.choice(keywords, size=len(sp)),
                "order_id": None, "promotion_id": promo_ids[sp],
            }))
        if len(rep_pos):
            event_frames.append(pd.DataFrame({
                "session_id": sid[rep_pos], "dt": d.isoformat(),
                "event_time": [f"{d} {t}" for t in _fmt_sec(exp_sec)],
                "member_id": member_ids[rep_pos], "user_type": user_type[rep_pos],
                "channel_id": channels[rep_pos], "device_type": devices[rep_pos],
                "event_type": "商品曝光", "page_type": "商品详情页",
                "product_id": exp_products, "search_keyword": None, "order_id": None,
                "promotion_id": promo_ids[rep_pos],
            }))
        if len(browse_pos):
            event_frames.append(pd.DataFrame({
                "session_id": sid[browse_pos], "dt": d.isoformat(),
                "event_time": [f"{d} {t}" for t in _fmt_sec(click_sec)],
                "member_id": member_ids[browse_pos], "user_type": user_type[browse_pos],
                "channel_id": channels[browse_pos], "device_type": devices[browse_pos],
                "event_type": "商品点击", "page_type": "商品详情页",
                "product_id": click_products, "search_keyword": None, "order_id": None,
                "promotion_id": promo_ids[browse_pos],
            }))
        if len(cart_pos):
            event_frames.append(pd.DataFrame({
                "session_id": sid[cart_pos], "dt": d.isoformat(),
                "event_time": [f"{d} {t}" for t in _fmt_sec(np.minimum(start_sec[cart_pos] + rng.integers(120, 1500, size=len(cart_pos)), 86399))],
                "member_id": member_ids[cart_pos], "user_type": user_type[cart_pos],
                "channel_id": channels[cart_pos], "device_type": devices[cart_pos],
                "event_type": "加入购物车", "page_type": "购物车",
                "product_id": cart_products, "search_keyword": None, "order_id": None,
                "promotion_id": promo_ids[cart_pos],
            }))
        if len(checkout_pos):
            event_frames.append(pd.DataFrame({
                "session_id": sid[checkout_pos], "dt": d.isoformat(),
                "event_time": [f"{d} {t}" for t in _fmt_sec(np.minimum(start_sec[checkout_pos] + rng.integers(180, 1600, size=len(checkout_pos)), 86399))],
                "member_id": member_ids[checkout_pos], "user_type": user_type[checkout_pos],
                "channel_id": channels[checkout_pos], "device_type": devices[checkout_pos],
                "event_type": "进入结算页", "page_type": "结算页",
                "product_id": None, "search_keyword": None, "order_id": None,
                "promotion_id": promo_ids[checkout_pos],
            }))
        if len(pay_pos):
            event_frames.append(pd.DataFrame({
                "session_id": sid[pay_pos], "dt": d.isoformat(),
                "event_time": [f"{d} {t}" for t in _fmt_sec(pay_sec[pay_pos])],
                "member_id": member_ids[pay_pos], "user_type": user_type[pay_pos],
                "channel_id": channels[pay_pos], "device_type": devices[pay_pos],
                "event_type": "支付成功", "page_type": "支付结果页",
                "product_id": None, "search_keyword": None,
                "order_id": order_ids[pay_pos], "promotion_id": promo_ids[pay_pos],
            }))
        events = pd.concat(event_frames, ignore_index=True)
        events.insert(0, "event_id", [f"EV{d:%Y%m%d}{i:08d}" for i in range(1, len(events) + 1)])
        events["update_time"] = events["event_time"]

        sessions = pd.DataFrame({
            "session_id": sid, "dt": d.isoformat(),
            "session_start_time": [f"{d} {t}" for t in _fmt_sec(start_sec)],
            "member_id": member_ids, "visitor_id": visitors,
            "channel_id": channels, "device_type": devices, "promotion_id": promo_ids,
            "entry_page": entry_pages, "is_browse": browse.astype(int), "is_search": search.astype(int),
            "is_cart": cart.astype(int), "is_checkout": checkout.astype(int), "is_paid": paid.astype(int),
            "order_id": order_ids,
            "update_time": [f"{d} {t}" for t in _fmt_sec(end_sec)],
        })

        n_events = writer.write_daily("behavior_event", events, d.isoformat())
        n_sess = writer.write_daily("online_session", sessions, d.isoformat())
        daily_counts[d.isoformat()] = {"online_session": n_sess, "behavior_event": n_events}

        if len(pay_pos):
            pref_products = []
            for pos in pay_pos:
                pref_products.append(click_map.get(int(pos)) or product_ids[int(rng.choice(loci, p=weights))])
            paid_member_ids = member_ids[pay_pos]
            orders = pd.DataFrame({
                "order_id": order_ids[pay_pos],
                "order_time": [f"{d} {t}" for t in _fmt_sec(pay_sec[pay_pos])],
                "dt": d.isoformat(),
                "store_id": www,
                "channel_id": channels[pay_pos],
                "member_id": paid_member_ids,
                "device_type": devices[pay_pos],
                "online_session_id": sid[pay_pos],
                "promotion_id": promo_ids[pay_pos],
                "order_status": "已完成",
                "create_time": [f"{d} {t}" for t in _fmt_sec(start_sec[pay_pos])],
                "update_time": [f"{d} {t}" for t in _fmt_sec(pay_sec[pay_pos])],
                "_preferred_product_id": pref_products,
            })
            online_orders.append(orders)

    orders_df = pd.concat(online_orders, ignore_index=True) if online_orders else pd.DataFrame()
    return orders_df, daily_counts
