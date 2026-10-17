"""会员、商品、促销、时间的抽样工具。"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

QTY_PROBS = {
    "食品饮料": [0.58, 0.25, 0.11, 0.06],
    "生鲜果蔬": [0.60, 0.24, 0.10, 0.06],
    "日化清洁": [0.72, 0.20, 0.06, 0.02],
    "家居百货": [0.80, 0.15, 0.04, 0.01],
    "服饰鞋包": [0.86, 0.11, 0.03, 0.00],
    "数码家电": [0.90, 0.08, 0.02, 0.00],
}

LINE_COUNT_PROBS = [0.28, 0.30, 0.22, 0.12, 0.08]  # 1..5 行，平均约 2.42


def sample_member_ids(
    rng: np.random.Generator,
    member_meta: dict,
    day: date,
    n: int,
    member_ratio: float,
) -> np.ndarray:
    """按注册日期和购买倾向抽取会员；未命中比例为游客（None）。"""
    if n <= 0:
        return np.array([], dtype=object)
    eligible = (member_meta["reg_ordinal"] <= day.toordinal()) & member_meta["purchasable"]
    idx = np.flatnonzero(eligible)
    if len(idx) == 0:
        return np.array([None] * n, dtype=object)
    p = member_meta["propensity"][idx].astype(float)
    if p.sum() <= 0:
        p = np.ones(len(idx))
    p = p / p.sum()
    chosen = rng.choice(idx, size=n, p=p)
    is_member = rng.random(n) < member_ratio
    ids = member_meta["member_id"][chosen].astype(object)
    return np.where(is_member, ids, None)


def sample_products(
    rng: np.random.Generator,
    master: dict,
    location_id: str,
    month: int,
    n: int,
    preferred_product_id: str | None = None,
) -> list[str]:
    if n <= 0:
        return []
    loci = master["assortment"][location_id]
    weights = master["sampling_weights"][(location_id, month)]
    picks = rng.choice(loci, size=n, p=weights)
    products = master["products"]
    if preferred_product_id:
        preferred_idx = products.index[products["product_id"] == preferred_product_id]
        if len(preferred_idx):
            pi = int(preferred_idx[0])
            if pi in set(loci.tolist()):
                picks[0] = pi
    return products.loc[picks, "product_id"].tolist()


def sample_quantities(
    rng: np.random.Generator,
    top_categories: list[str],
    n: int,
) -> np.ndarray:
    out = np.ones(n, dtype=int)
    for top in set(top_categories):
        positions = np.array([i for i, t in enumerate(top_categories) if t == top])
        probs = QTY_PROBS[top]
        choices = rng.choice([1, 2, 3, 4], size=len(positions), p=probs)
        out[positions] = choices
    return out


def sample_line_counts(rng: np.random.Generator, n_orders: int) -> np.ndarray:
    return rng.choice([1, 2, 3, 4, 5], size=n_orders, p=LINE_COUNT_PROBS)


def select_promotion(
    rng: np.random.Generator,
    promotions_by_date: dict[str, list[dict]],
    d: date,
    is_member: bool,
    channel_type: str,
    apply_prob: float = 0.75,
) -> dict | None:
    candidates = promotions_by_date.get(d.isoformat(), [])
    if not candidates:
        return None
    usable = []
    for p in candidates:
        if int(p.get("_member_only", 0)) == 1 and not is_member:
            continue
        scope = p.get("channel_scope", "全渠道")
        if scope != "全渠道" and scope != channel_type:
            continue
        usable.append(p)
    if not usable:
        return None
    if rng.random() > apply_prob:
        return None
    # 越高折扣力度越优先，重叠活动取最高力度
    return max(usable, key=lambda p: float(p["discount_rate"]))


def sample_store_hour(rng: np.random.Generator, n: int) -> np.ndarray:
    hours = np.arange(10, 22)
    weights = np.array([0.045, 0.055, 0.075, 0.09, 0.105, 0.095, 0.075, 0.07, 0.08, 0.10, 0.11, 0.10])
    weights = weights / weights.sum()
    return rng.choice(hours, size=n, p=weights)


def sample_online_hour(rng: np.random.Generator, n: int) -> np.ndarray:
    hours = np.arange(8, 24)
    weights = np.array([0.02, 0.035, 0.045, 0.055, 0.06, 0.055, 0.05, 0.05, 0.06, 0.07, 0.09, 0.105, 0.11, 0.095, 0.065, 0.035])
    weights = weights / weights.sum()
    return rng.choice(hours, size=n, p=weights)


def random_times(
    rng: np.random.Generator,
    days: pd.Series,
    hours: np.ndarray,
    n: int | None = None,
) -> pd.Series:
    """在指定日期上按小时分布生成随机秒级时间字符串。"""
    size = len(days) if n is None else n
    minute = rng.integers(0, 60, size=size)
    second = rng.integers(0, 60, size=size)
    strings = []
    for d, h, m, s in zip(days, hours, minute, second):
        strings.append(f"{d} {int(h):02d}:{int(m):02d}:{int(s):02d}")
    return pd.Series(strings)
