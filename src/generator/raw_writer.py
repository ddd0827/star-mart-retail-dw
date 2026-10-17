"""模拟源系统落盘与脏数据注入。

所有脏数据只写入 raw 层；内存中的干净数据用于生成下游事实，
确保订单、支付、退款、库存之间仍可对账。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.config import Config
from src.common.schemas import RAW_SCHEMAS


@dataclass
class DirtyStats:
    injected: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, value: int) -> None:
        if value:
            self.injected[key] = self.injected.get(key, 0) + int(value)

    def merge(self, other: "DirtyStats") -> None:
        for key, value in other.injected.items():
            self.add(key, value)


def _mixed_timestamp(series: pd.Series, mask: np.ndarray) -> pd.Series:
    out = series.copy()
    idx = out.index[mask]
    if len(idx) == 0:
        return out
    out.loc[idx] = out.loc[idx].astype(str).str.replace("-", "/", regex=False)
    return out


def _duplicate(df: pd.DataFrame, ratio: float, rng: np.random.Generator) -> tuple[pd.DataFrame, int]:
    n = int(len(df) * ratio)
    if n <= 0 or len(df) == 0:
        return df, 0
    dup = df.sample(n=n, random_state=int(rng.integers(0, 2**31 - 1)))
    return pd.concat([df, dup], ignore_index=True), n


def inject_dim_dirty(
    table: str,
    df: pd.DataFrame,
    rng: np.random.Generator,
    ratios: dict,
    enabled: bool = True,
) -> tuple[pd.DataFrame, DirtyStats]:
    stats = DirtyStats()
    if not enabled or len(df) == 0:
        return df, stats
    df = df.copy().reset_index(drop=True)

    if table in ("product_info", "store_info", "member_info"):
        df, n = _duplicate(df, ratios.get("duplicate_member", 0.001), rng)
        stats.add("duplicate_rows", n)

    if table == "product_info":
        n_price = max(1, int(len(df) * ratios.get("negative_product_price", 0.001)))
        idx = rng.choice(df.index, size=min(n_price, len(df)), replace=False)
        df.loc[idx, "list_price"] = -df.loc[idx, "list_price"].astype(float).abs()
        stats.add("negative_price", len(idx))

        n_ws = max(1, int(len(df) * ratios.get("whitespace_dimension", 0.01)))
        idx = rng.choice(df.index, size=min(n_ws, len(df)), replace=False)
        df.loc[idx, "product_name"] = df.loc[idx, "product_name"].astype(str) + "  "
        stats.add("whitespace_name", len(idx))

    if table == "store_info":
        n_ws = max(1, int(len(df) * ratios.get("whitespace_dimension", 0.01)))
        idx = rng.choice(df.index, size=min(n_ws, len(df)), replace=False)
        df.loc[idx, "store_name"] = df.loc[idx, "store_name"].astype(str) + " "
        stats.add("whitespace_name", len(idx))

    return df, stats


def inject_fact_dirty(
    table: str,
    df: pd.DataFrame,
    rng: np.random.Generator,
    ratios: dict,
    enabled: bool = True,
    canceled_order_ids: set[str] | None = None,
    mixed_timestamp_prob: float | None = None,
) -> tuple[pd.DataFrame, DirtyStats]:
    stats = DirtyStats()
    if not enabled or len(df) == 0:
        return df, stats
    df = df.copy().reset_index(drop=True)
    mixed_p = ratios.get("mixed_timestamp", 0.005) if mixed_timestamp_prob is None else mixed_timestamp_prob

    def add_duplicate(ratio_key: str, label: str) -> None:
        nonlocal df
        df, n = _duplicate(df, ratios.get(ratio_key, 0.002), rng)
        stats.add(label, n)

    def add_mixed(cols: list[str]) -> None:
        mask = rng.random(len(df)) < mixed_p
        for col in cols:
            if col in df.columns:
                df[col] = _mixed_timestamp(df[col], mask)
        stats.add("mixed_timestamp", int(mask.sum()))

    if table == "order_info":
        add_duplicate("duplicate_order", "duplicate_rows")
        add_mixed(["order_time", "create_time", "update_time"])
        n_null = max(1, int(len(df) * ratios.get("null_store", 0.001)))
        idx = rng.choice(df.index, size=min(n_null, len(df)), replace=False)
        df.loc[idx, "store_id"] = None
        stats.add("null_store", len(idx))
        n_unknown = max(1, int(len(df) * ratios.get("unknown_member", 0.001)))
        idx = rng.choice(df.index, size=min(n_unknown, len(df)), replace=False)
        df.loc[idx, "member_id"] = "M9999999"
        stats.add("unknown_member", len(idx))

    elif table == "order_detail":
        add_duplicate("duplicate_order", "duplicate_rows")
        add_mixed(["update_time"])
        if canceled_order_ids:
            mask = df["order_id"].isin(canceled_order_ids).to_numpy()
            candidates = np.flatnonzero(mask)
            if len(candidates):
                n_bad = max(1, int(len(df) * ratios.get("invalid_qty_canceled", 0.05)))
                pick = rng.choice(candidates, size=min(n_bad, len(candidates)), replace=False)
                df.loc[pick, "quantity"] = -1
                stats.add("invalid_quantity", len(pick))

    elif table == "payment_info":
        add_duplicate("duplicate_payment", "duplicate_rows")
        add_mixed(["pay_time", "update_time"])

    elif table == "refund_info":
        add_duplicate("duplicate_order", "duplicate_rows")
        add_mixed(["refund_time", "update_time"])

    elif table == "online_session":
        add_duplicate("duplicate_order", "duplicate_rows")
        add_mixed(["session_start_time", "update_time"])

    elif table == "behavior_event":
        add_duplicate("duplicate_event", "duplicate_rows")
        add_mixed(["event_time", "update_time"])

    elif table in ("inventory_snapshot", "store_traffic_daily", "purchase_order"):
        add_duplicate("duplicate_order", "duplicate_rows")
        if table == "purchase_order":
            add_mixed(["order_date", "expected_arrival_date", "update_time"])

    return df, stats


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8", float_format="%.2f")


class RawWriter:
    def __init__(self, config: Config, rng: np.random.Generator, enabled: bool = True):
        self.config = config
        self.rng = rng
        self.enabled = enabled
        self.ratios = config.get("generator.dirty_ratios", {})
        self.table_counts: dict[str, int] = {}
        self.daily_counts: dict[str, dict[str, int]] = {}
        self.dirty = DirtyStats()

    def _record(self, table: str, dt: str | None, rows: int) -> None:
        self.table_counts[table] = self.table_counts.get(table, 0) + rows
        if dt is not None:
            self.daily_counts.setdefault(dt, {})
            self.daily_counts[dt][table] = self.daily_counts[dt].get(table, 0) + rows

    def write_dim(self, table: str, df: pd.DataFrame) -> int:
        df = df.reindex(columns=RAW_SCHEMAS[table].fieldNames())
        clean_rows = len(df)
        df, stats = inject_dim_dirty(table, df, self.rng, self.ratios, self.enabled)
        self.dirty.merge(stats)
        path = self.config.path("raw") / table / f"{table}.csv"
        _write_csv(df, path)
        self._record(table, None, len(df))
        return clean_rows

    def write_daily(
        self,
        table: str,
        df: pd.DataFrame,
        dt: str,
        canceled_order_ids: set[str] | None = None,
        mixed_timestamp_prob: float | None = None,
    ) -> int:
        if len(df) == 0:
            return 0
        df = df.reindex(columns=RAW_SCHEMAS[table].fieldNames())
        clean_rows = len(df)
        df, stats = inject_fact_dirty(
            table,
            df,
            self.rng,
            self.ratios,
            self.enabled,
            canceled_order_ids=canceled_order_ids,
            mixed_timestamp_prob=mixed_timestamp_prob,
        )
        self.dirty.merge(stats)
        path = self.config.path("raw") / table / f"dt={dt}" / f"{table}_part-00000.csv"
        _write_csv(df, path)
        self._record(table, dt, len(df))
        return clean_rows
