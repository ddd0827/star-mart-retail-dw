"""门店日客流生成。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.common.calendar_cn import calendar_factor, is_holiday

PROMO_TRAFFIC_UPLIFT = {
    "五一欢乐购": 1.16,
    "618年中大促": 1.06,
    "端午安康": 1.08,
    "中秋团圆节": 1.10,
    "国庆黄金周": 1.26,
}


def generate_store_traffic(config, master: dict, rng: np.random.Generator) -> pd.DataFrame:
    stores = master["store_simulation"]
    offline = stores[stores["is_offline"] == 1].reset_index(drop=True)
    dates = config.date_list()
    n_days = len(dates)
    rows = []
    for day_idx, d in enumerate(dates):
        progress = day_idx / max(1, n_days - 1)
        trend = 0.96 + 0.10 * progress
        promo_list = master["promotions_by_date"].get(d.isoformat(), [])
        uplift = 1.0
        for p in promo_list:
            if int(p.get("_member_only", 0)) == 1:
                uplift = max(uplift, 1.04)
            else:
                uplift = max(uplift, PROMO_TRAFFIC_UPLIFT.get(p["promotion_name"], 1.05))
        traffic_scale = float(config.get("generator.store_traffic_factor", 1.0))
        for _, store in offline.iterrows():
            mean = (
                float(store["_base_footfall"])
                * traffic_scale
                * calendar_factor(d)
                * trend
                * uplift
                * rng.uniform(0.90, 1.10)
            )
            traffic = max(20, int(rng.poisson(max(mean, 1.0))))
            rows.append({
                "dt": d.isoformat(),
                "store_id": store["store_id"],
                "traffic_in": traffic,
                "update_time": f"{d.isoformat()} 23:00:00",
            })
    return pd.DataFrame(rows)
