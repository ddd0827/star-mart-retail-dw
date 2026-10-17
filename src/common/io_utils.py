"""Parquet 数仓读写与分区幂等工具。"""
from __future__ import annotations

import json
import shutil
import time
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DateType, IntegerType, StructField, StructType, TimestampType

from .config import Config


def parquet_path(config: Config, layer: str, table: str) -> Path:
    return config.path("warehouse") / layer / table


def _remove_partition_dirs(path: Path, dates: Iterable[str], partition_col: str = "dt") -> None:
    for d in dates:
        part = path / f"{partition_col}={d}"
        if part.exists():
            for attempt in range(3):
                try:
                    shutil.rmtree(part)
                    break
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(1.0)


def write_partitioned(
    df: DataFrame,
    path: Path,
    dates: Sequence[str],
    partition_col: str = "dt",
    num_partitions: int | None = None,
    is_empty: bool | None = None,
) -> None:
    """按 dt 幂等写入：先删目标分区，再 append。

    空结果使用非分区空 Parquet 保存 Schema，避免下游无法推断 Schema。
    """
    path.mkdir(parents=True, exist_ok=True)
    dates = list(dict.fromkeys(dates))
    if is_empty is None:
        is_empty = len(df.take(1)) == 0
    dummy_dt = "1900-01-01"
    _remove_partition_dirs(path, [dummy_dt], partition_col)
    empty_dir = path / "_empty"
    if empty_dir.exists():
        shutil.rmtree(empty_dir, ignore_errors=True)
    if is_empty:
        _remove_partition_dirs(path, dates, partition_col)
        # 写一个 dt=1900-01-01 的占位行以保留 Schema；读取时按日期过滤排除。
        fields = df.schema.fieldNames()
        row = [None] * len(fields)
        dt_field = df.schema[fields.index(partition_col)]
        if isinstance(dt_field.dataType, DateType):
            row[fields.index(partition_col)] = date(1900, 1, 1)
        elif isinstance(dt_field.dataType, TimestampType):
            row[fields.index(partition_col)] = datetime(1900, 1, 1)
        elif isinstance(dt_field.dataType, IntegerType):
            row[fields.index(partition_col)] = 19000101
        else:
            row[fields.index(partition_col)] = dummy_dt
        nullable_schema = StructType([StructField(f.name, f.dataType, True) for f in df.schema])
        dummy = df.sparkSession.createDataFrame([tuple(row)], schema=nullable_schema)
        dummy.write.mode("append").partitionBy(partition_col).parquet(path.as_posix())
        return
    _remove_partition_dirs(path, dates, partition_col)
    n = num_partitions or max(1, len(dates))
    if n > 1:
        df = df.repartition(n, F.col(partition_col))
    else:
        df = df.coalesce(1)
    df.write.mode("append").partitionBy(partition_col).parquet(path.as_posix())


def write_snapshot(df: DataFrame, path: Path, num_partitions: int = 1) -> None:
    """全量覆盖快照表（维表、RFM 等）。"""
    path.mkdir(parents=True, exist_ok=True)
    if num_partitions > 0:
        df = df.repartition(num_partitions)
    df.write.mode("overwrite").parquet(path.as_posix())


def read_parquet(
    spark: SparkSession,
    path: Path,
    dt_from: str | None = None,
    dt_to: str | None = None,
    dt_col: str = "dt",
):
    df = spark.read.parquet(path.as_posix())
    if dt_from is not None and dt_col in df.columns:
        df = df.filter(F.col(dt_col) >= dt_from)
    if dt_to is not None and dt_col in df.columns:
        df = df.filter(F.col(dt_col) <= dt_to)
    return df


def register_view(
    spark: SparkSession,
    path: Path,
    view: str,
    dt_from: str | None = None,
    dt_to: str | None = None,
    cache: bool = False,
):
    df = read_parquet(spark, path, dt_from, dt_to)
    if cache:
        df = df.cache()
    df.createOrReplaceTempView(view)
    return df


def register_table(
    spark: SparkSession,
    config: Config,
    layer: str,
    table: str,
    dt_from: str | None = None,
    dt_to: str | None = None,
    view: str | None = None,
    cache: bool = False,
):
    return register_view(
        spark,
        parquet_path(config, layer, table),
        view or table,
        dt_from=dt_from,
        dt_to=dt_to,
        cache=cache,
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def render_sql(sql: str, params: dict[str, str]) -> str:
    rendered = sql
    for key, value in params.items():
        rendered = rendered.replace("${" + key + "}", str(value))
    return rendered


def run_sql_file(
    spark: SparkSession,
    sql_path: Path,
    params: dict[str, str],
) -> DataFrame:
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    return spark.sql(render_sql(sql, params))
