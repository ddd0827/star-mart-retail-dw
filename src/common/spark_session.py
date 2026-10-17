"""SparkSession 工厂（Windows 本地模式）。"""
from __future__ import annotations

from .env import configure_environment, project_root

# 必须在导入 pyspark 前完成环境变量设置
configure_environment()

from pyspark.sql import SparkSession  # noqa: E402

from .config import Config  # noqa: E402


def get_spark(config: Config, app_name: str | None = None) -> SparkSession:
    root = project_root()
    spark_cfg = config.spark_cfg
    warehouse = (config.path("warehouse") / "_spark_warehouse").as_posix()
    local_dir = (root / "tmp" / "spark").as_posix()
    hadoop_home = (root / "env" / "hadoop").as_posix()
    root_uri = root.as_uri()

    session = (
        SparkSession.builder.appName(app_name or config.project["name"])
        .master(spark_cfg.get("master", "local[4]"))
        .config("spark.driver.memory", spark_cfg.get("driver_memory", "5g"))
        .config("spark.sql.shuffle.partitions", str(spark_cfg.get("shuffle_partitions", 32)))
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.adaptive.skewJoin.enabled", "true")
        .config("spark.sql.session.timeZone", config.project.get("timezone", "Asia/Shanghai"))
        .config("spark.sql.parquet.compression.codec", spark_cfg.get("parquet_compression", "snappy"))
        .config("spark.sql.files.maxRecordsPerFile", str(spark_cfg.get("max_records_per_file", 1_000_000)))
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.sql.execution.arrow.pyspark.enabled", "false")
        .config("spark.sql.warehouse.dir", f"{root_uri}/data/warehouse/_spark_warehouse")
        .config("spark.local.dir", local_dir)
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.hadoop.hadoop.home.dir", hadoop_home)
        .config("spark.hadoop.fs.file.impl.disable.cache", "true")
        .config("spark.driver.maxResultSize", "1g")
        .config("spark.sql.autoBroadcastJoinThreshold", str(64 * 1024 * 1024))
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("WARN")
    return session
