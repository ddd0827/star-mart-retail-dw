"""2026 年中国法定节假日与营业日历。

仅覆盖数据窗口所在的日期；未建模调休上班日。
"""
from __future__ import annotations

from datetime import date, timedelta

HOLIDAYS_2026: dict[str, str] = {}


def _add_range(start: str, end: str, name: str) -> None:
    d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while d <= end_d:
        HOLIDAYS_2026[d.isoformat()] = name
        d += timedelta(days=1)


_add_range("2026-05-01", "2026-05-05", "劳动节")
_add_range("2026-06-19", "2026-06-21", "端午节")
_add_range("2026-09-25", "2026-09-27", "中秋节")
_add_range("2026-10-01", "2026-10-07", "国庆节")

WEEKDAY_FACTOR = {
    0: 0.88,  # 周一
    1: 0.90,
    2: 0.92,
    3: 0.95,
    4: 1.06,  # 周五
    5: 1.34,  # 周六
    6: 1.22,  # 周日
}


def holiday_name(d: date) -> str | None:
    return HOLIDAYS_2026.get(d.isoformat())


def is_holiday(d: date) -> bool:
    return d.isoformat() in HOLIDAYS_2026


def calendar_factor(d: date) -> float:
    """营业日基础系数：节假日 > 周末 > 工作日。"""
    if is_holiday(d):
        name = holiday_name(d)
        if name in ("劳动节", "国庆节"):
            return 1.55
        return 1.30
    return WEEKDAY_FACTOR[d.weekday()]
