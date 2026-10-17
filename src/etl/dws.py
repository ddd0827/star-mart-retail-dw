"""DWS 层：交易、会员、线上漏斗、库存、活动主题日汇总。"""
from __future__ import annotations

import time

from pyspark.sql import SparkSession

from src.common.config import Config
from src.common.io_utils import parquet_path, register_table, run_sql_file, write_partitioned
from src.common.logger import get_logger

DWS_TABLES = [
    "dws_trade_store_day",
    "dws_trade_channel_day",
    "dws_trade_sku_day",
    "dws_member_day",
    "dws_online_funnel_day",
    "dws_inventory_sku_day",
    "dws_trade_campaign_day",
]

DWD_INPUTS = [
    "dwd_order_info", "dwd_order_detail", "dwd_refund", "dwd_store_traffic",
    "dwd_online_session", "dwd_inventory_snapshot",
]


def run_dws(spark: SparkSession, config: Config) -> dict:
    logger = get_logger()
    t0 = time.time()
    logger.info("DWS 层构建开始")
    start, end = config.start_date.isoformat(), config.end_date.isoformat()

    cached = []
    for table in DWD_INPUTS:
        path = parquet_path(config, "dwd", table)
        if not path.exists():
            logger.warning("DWD 表不存在，跳过: %s", table)
            continue
        use_cache = table in ("dwd_order_info", "dwd_order_detail", "dwd_refund")
        df = register_table(spark, config, "dwd", table, start, end, view=table, cache=use_cache)
        if use_cache:
            cached.append(df)
    for dim in ("dim_member", "dim_promotion", "dim_store", "dim_product"):
        register_table(spark, config, "dim", dim, view=dim)

    counts = {}
    sql_dir = config.root / "src" / "sql" / "dws"
    for table in DWS_TABLES:
        logger.info("  DWS SQL: %s", table)
        df = run_sql_file(spark, sql_dir / f"{table}.sql", {})
        n = df.count()
        write_partitioned(df, parquet_path(config, "dws", table), config.dt_list())
        counts[table] = n
        logger.info("  DWS %-28s %12d 行", table, n)
        df.createOrReplaceTempView(table)

    for df in cached:
        df.unpersist()
    logger.info("DWS 层完成，用时 %.1f 秒", time.time() - t0)
    return counts
