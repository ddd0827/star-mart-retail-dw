"""ADS 结果导出为 CSV（UTF-8 BOM）与 JSON。"""
from __future__ import annotations

import json
import time

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from src.common.config import Config
from src.common.io_utils import parquet_path, write_json
from src.common.logger import get_logger

ADS_TABLES = [
    "ads_operation_overview",
    "ads_store_performance",
    "ads_category_structure",
    "ads_product_topn",
    "ads_member_rfm",
    "ads_member_retention",
    "ads_member_repurchase",
    "ads_inventory_turnover",
    "ads_online_funnel",
    "ads_promotion_effect",
]

SORT_COLUMNS = {
    "ads_operation_overview": ["dt"],
    "ads_store_performance": ["dt", "gmv"],
    "ads_category_structure": ["dt", "sales_amount"],
    "ads_product_topn": ["overall_rank"],
    "ads_member_rfm": ["rfm_segment", "monetary"],
    "ads_member_retention": ["cohort_month", "months_diff"],
    "ads_member_repurchase": ["stat_month"],
    "ads_inventory_turnover": ["dt", "location_id"],
    "ads_online_funnel": ["dt", "channel_id"],
    "ads_promotion_effect": ["start_date", "channel_id"],
}


def export_ads(spark: SparkSession, config: Config) -> dict:
    logger = get_logger()
    t0 = time.time()
    out_dir = config.path("ads_export")
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = config.start_date.isoformat(), config.end_date.isoformat()
    counts = {}
    files = {}

    for table in ADS_TABLES:
        path = parquet_path(config, "ads", table)
        if not path.exists():
            logger.warning("ADS 表不存在，跳过导出: %s", table)
            continue
        df = spark.read.parquet(path.as_posix())
        if "dt" in df.columns:
            df = df.filter(F.col("dt") >= start).filter(F.col("dt") <= end)
        pdf = df.toPandas()
        sort_cols = [c for c in SORT_COLUMNS.get(table, []) if c in pdf.columns]
        if sort_cols:
            pdf = pdf.sort_values(sort_cols, ascending=[False if c not in ("dt", "cohort_month", "stat_month", "months_diff", "overall_rank", "start_date") else True for c in sort_cols])
        out_file = out_dir / f"{table}.csv"
        pdf.to_csv(out_file, index=False, encoding="utf-8-sig")
        json_file = out_dir / f"{table}.json"
        clean = pdf.astype(object).where(pd.notna(pdf), None)
        json_file.write_text(
            json.dumps(clean.to_dict(orient="records"), ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        counts[table] = len(pdf)
        files[table] = {"csv": str(out_file), "json": str(json_file)}
        logger.info("  导出 %-28s %8d 行 -> %s / %s", table, len(pdf), out_file.name, json_file.name)

    manifest = {
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": start,
        "end_date": end,
        "row_counts": counts,
        "files": files,
        "seconds": round(time.time() - t0, 2),
    }
    write_json(out_dir / "_manifest.json", manifest)
    logger.info("ADS 导出完成（CSV + JSON），用时 %.1f 秒", time.time() - t0)
    return counts
