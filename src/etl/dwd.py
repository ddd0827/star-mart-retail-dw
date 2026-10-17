"""DWD 层：清洗、去重、维度补全与可信事实表。"""
from __future__ import annotations

import time

from pyspark.sql import SparkSession

from src.common.config import Config
from src.common.io_utils import parquet_path, register_table, run_sql_file, write_partitioned
from src.common.logger import get_logger

SQL_DIR = __file__.rsplit("etl", 1)[0] + "sql/dwd"

ODS_FACT_TABLES = [
    "order_info", "order_detail", "payment_info", "refund_info",
    "inventory_snapshot", "store_traffic_daily", "online_session",
    "behavior_event", "purchase_order",
]
DIM_TABLES = ["dim_store", "dim_channel", "dim_member", "dim_promotion", "dim_product",
              "dim_supplier", "dim_category", "dim_brand"]


def run_dwd(spark: SparkSession, config: Config) -> dict:
    logger = get_logger()
    t0 = time.time()
    logger.info("DWD 层构建开始")

    available_ods = set()
    for table in ODS_FACT_TABLES:
        path = parquet_path(config, "ods", table)
        if not path.exists():
            logger.warning("ODS 表不存在，跳过 DWD 源: %s", table)
            continue
        register_table(spark, config, "ods", table, config.start_date.isoformat(), config.end_date.isoformat(),
                       view=f"ods_{table}")
        available_ods.add(table)
    for table in DIM_TABLES:
        register_table(spark, config, "dim", table, view=table)

    dates = config.dt_list()
    counts = {}
    sql_dir = config.root / "src" / "sql" / "dwd"

    def run(name: str, view: str | None = None):
        logger.info("  DWD SQL: %s", name)
        df = run_sql_file(spark, sql_dir / f"{name}.sql", {})
        out_view = view or name
        df.createOrReplaceTempView(out_view)
        return df

    def write_table(df, name: str, cache: bool = False, dates_override=None):
        if cache:
            df = df.cache()
        n = df.count()
        write_partitioned(df, parquet_path(config, "dwd", name), dates_override or dates)
        counts[name] = n
        logger.info("  DWD %-24s %12d 行", name, n)
        return df

    # 订单主表是后续支付/退款/明细的公共输入，短暂缓存
    order_info = run("dwd_order_info")
    order_info = write_table(order_info, "dwd_order_info", cache=True)

    detail = run("dwd_order_detail")
    detail = detail.cache()
    n_detail = detail.count()
    write_partitioned(detail, parquet_path(config, "dwd", "dwd_order_detail"), dates)
    counts["dwd_order_detail"] = n_detail
    logger.info("  DWD %-24s %12d 行", "dwd_order_detail", n_detail)

    payment = run("dwd_payment")
    write_table(payment, "dwd_payment")

    refund = run("dwd_refund")
    write_table(refund, "dwd_refund")

    inv = run("dwd_inventory_snapshot")
    write_table(inv, "dwd_inventory_snapshot")

    traffic = run("dwd_store_traffic")
    write_table(traffic, "dwd_store_traffic")

    session = run("dwd_online_session")
    write_table(session, "dwd_online_session")

    behavior = run("dwd_behavior_event")
    write_table(behavior, "dwd_behavior_event")

    if "purchase_order" in available_ods:
        purchase = run("dwd_purchase_order")
        write_table(purchase, "dwd_purchase_order")
    else:
        logger.warning("无采购源数据，跳过 dwd_purchase_order")

    detail.unpersist()
    order_info.unpersist()
    logger.info("DWD 层完成，用时 %.1f 秒", time.time() - t0)
    return counts
