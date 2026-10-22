"""Power BI 数据集导出：星型模型 CSV、DAX 度量、主题与建模说明。

用法（项目根目录）：
    .venv\\Scripts\\python.exe -m src.report.powerbi

输出目录 output/powerbi/：
    data/           维度表与事实表 CSV（UTF-8 BOM）
    theme/          Power BI 主题 JSON
    measures.dax    DAX 度量
    README.md       导入与建模说明
    _manifest.json  行数、关系与文件清单
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

from src.common.config import Config
from src.common.io_utils import write_json
from src.common.logger import get_logger, setup_logger

# 事实表 -> (ADS 表名, 需要移除的冗余列)
FACT_SPECS: dict[str, tuple[str, list[str]]] = {
    "fact_operation_day": ("ads_operation_overview", ["etl_time"]),
    "fact_store_day": (
        "ads_store_performance",
        ["etl_time", "store_name", "store_type", "city_id", "region_id"],
    ),
    "fact_category_day": (
        "ads_category_structure",
        ["etl_time", "category_name", "top_category_name"],
    ),
    "fact_product_snapshot": (
        "ads_product_topn",
        ["etl_time", "product_name", "category_name", "top_category_name", "brand_name"],
    ),
    "fact_member_rfm": ("ads_member_rfm", ["etl_time"]),
    "fact_retention": ("ads_member_retention", ["etl_time"]),
    "fact_repurchase": ("ads_member_repurchase", ["etl_time"]),
    "fact_inventory_day": (
        "ads_inventory_turnover",
        ["etl_time", "location_name", "store_type", "is_offline", "sk_location"],
    ),
    "fact_funnel_day": ("ads_online_funnel", ["etl_time", "channel_type", "sk_channel"]),
    "fact_promotion": ("ads_promotion_effect", ["etl_time", "channel_name"]),
}

# Power BI 关系：事实表列 -> 维度表列（多对一）
RELATIONSHIPS: list[dict[str, str]] = [
    {"fact": "fact_operation_day", "fact_column": "dt", "dim": "dim_date", "dim_column": "date"},
    {"fact": "fact_store_day", "fact_column": "dt", "dim": "dim_date", "dim_column": "date"},
    {"fact": "fact_store_day", "fact_column": "store_id", "dim": "dim_store", "dim_column": "store_id"},
    {"fact": "fact_category_day", "fact_column": "dt", "dim": "dim_date", "dim_column": "date"},
    {"fact": "fact_category_day", "fact_column": "category_id", "dim": "dim_category", "dim_column": "category_id"},
    {"fact": "fact_product_snapshot", "fact_column": "dt", "dim": "dim_date", "dim_column": "date"},
    {"fact": "fact_product_snapshot", "fact_column": "product_id", "dim": "dim_product", "dim_column": "product_id"},
    {"fact": "fact_member_rfm", "fact_column": "dt", "dim": "dim_date", "dim_column": "date"},
    {"fact": "fact_member_rfm", "fact_column": "member_id", "dim": "dim_member", "dim_column": "member_id"},
    {"fact": "fact_inventory_day", "fact_column": "dt", "dim": "dim_date", "dim_column": "date"},
    {"fact": "fact_inventory_day", "fact_column": "location_id", "dim": "dim_store", "dim_column": "store_id"},
    {"fact": "fact_funnel_day", "fact_column": "dt", "dim": "dim_date", "dim_column": "date"},
    {"fact": "fact_funnel_day", "fact_column": "channel_id", "dim": "dim_channel", "dim_column": "channel_id"},
    {"fact": "fact_promotion", "fact_column": "channel_id", "dim": "dim_channel", "dim_column": "channel_id"},
    {"fact": "fact_repurchase", "fact_column": "stat_month", "dim": "dim_month", "dim_column": "month_key"},
    {"fact": "fact_retention", "fact_column": "stat_month", "dim": "dim_month", "dim_column": "month_key"},
    {"fact": "dim_product", "fact_column": "category_id", "dim": "dim_category", "dim_column": "category_id"},
]


def _read_dim(config: Config, name: str) -> pd.DataFrame:
    path = config.path("warehouse") / "dim" / name
    if not path.exists():
        raise FileNotFoundError(f"缺少维度表: {path}，请先运行 DIM 阶段")
    return ds.dataset(path.as_posix(), format="parquet").to_table().to_pandas()


def _read_ads(config: Config, name: str) -> pd.DataFrame:
    path = config.path("ads_export") / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"缺少 ADS 导出: {path}，请先运行 EXPORT 阶段")
    return pd.read_csv(path, encoding="utf-8-sig")


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")


def _drop(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df.drop(columns=[c for c in columns if c in df.columns])


def _build_dimensions(config: Config, data_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    start, end = config.start_date.isoformat(), config.end_date.isoformat()

    store = _read_dim(config, "dim_store")[[
        "store_id", "store_name", "store_type", "city_id", "city_name",
        "province", "region_id", "region_name", "is_offline", "status",
    ]].copy()
    store["is_offline"] = store["is_offline"].astype(int)

    category = _read_dim(config, "dim_category")[[
        "category_id", "category_name", "parent_id", "level",
        "top_category_id", "top_category_name",
    ]].copy()
    # 脏数据会产生无法归属品类的退款行，保留为未知品类，避免退款金额丢失
    unknown_category = pd.DataFrame([{
        "category_id": "__UNKNOWN__",
        "category_name": "未知品类",
        "parent_id": None,
        "level": 0,
        "top_category_id": "__UNKNOWN__",
        "top_category_name": "未知品类",
    }])
    category = pd.concat([category, unknown_category], ignore_index=True)

    product = _read_dim(config, "dim_product")[[
        "product_id", "product_name", "category_id", "category_name",
        "top_category_id", "top_category_name", "brand_id", "brand_name",
        "supplier_id", "supplier_name", "list_price", "cost_price",
        "unit", "spec", "status",
    ]].copy()

    channel = _read_dim(config, "dim_channel")[["channel_id", "channel_name", "channel_type"]].copy()

    member = _read_dim(config, "dim_member")[[
        "member_id", "gender", "age_group", "city_id",
        "register_channel", "member_level", "register_date", "member_status",
    ]].copy()
    city_map = store[["city_id", "city_name"]].drop_duplicates().set_index("city_id")["city_name"]
    member["city_name"] = member["city_id"].map(city_map).fillna("未知城市")
    member["register_date"] = pd.to_datetime(member["register_date"]).dt.strftime("%Y-%m-%d")

    dates = _read_dim(config, "dim_date")[[
        "date", "year", "quarter", "month", "day", "week_of_year",
        "day_of_week", "day_name_cn", "is_weekend", "is_holiday", "holiday_name",
    ]].copy()
    dates["date"] = pd.to_datetime(dates["date"]).dt.strftime("%Y-%m-%d")
    dates = dates[(dates["date"] >= start) & (dates["date"] <= end)].sort_values("date")
    for col in ("is_weekend", "is_holiday"):
        dates[col] = dates[col].astype(int)

    # 留存分析会延伸到当前数据窗口之后的未观测月份，月份维度需覆盖这些 stat_month
    month_keys = set(dates["date"].str[:7])
    for ads_name, columns in (
        ("ads_member_retention", ["cohort_month", "stat_month"]),
        ("ads_member_repurchase", ["stat_month"]),
    ):
        df = _read_ads(config, ads_name)
        for column in columns:
            if column in df.columns:
                month_keys.update(df[column].dropna().astype(str))
    month = pd.DataFrame({"month_key": sorted(month_keys)})
    month_start = pd.to_datetime(month["month_key"] + "-01")
    month["year"] = month_start.dt.year
    month["quarter"] = month_start.dt.quarter
    month["month"] = month_start.dt.month
    month["month_label"] = (
        month["year"].astype(str) + "年" + month["month"].astype(str).str.zfill(2) + "月"
    )
    month["month_start"] = month_start.dt.strftime("%Y-%m-%d")
    month["month_end"] = (month_start + pd.offsets.MonthEnd(0)).dt.strftime("%Y-%m-%d")
    month = month[["month_key", "year", "quarter", "month", "month_label", "month_start", "month_end"]]

    tables = {
        "dim_date": dates,
        "dim_month": month,
        "dim_store": store,
        "dim_category": category,
        "dim_product": product,
        "dim_channel": channel,
        "dim_member": member,
    }
    for name, df in tables.items():
        _write_csv(df, data_dir / f"{name}.csv")
        counts[name] = len(df)
    return counts


def _build_facts(config: Config, data_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for fact_name, (ads_name, drop_cols) in FACT_SPECS.items():
        df = _drop(_read_ads(config, ads_name), drop_cols)
        if fact_name == "fact_category_day":
            for column in ("category_id", "top_category_id"):
                if column in df.columns:
                    df[column] = df[column].fillna("__UNKNOWN__")
        if fact_name == "fact_retention" and "stat_month_end" in df.columns:
            df["stat_month_end"] = pd.to_datetime(df["stat_month_end"]).dt.strftime("%Y-%m-%d")
        _write_csv(df, data_dir / f"{fact_name}.csv")
        counts[fact_name] = len(df)
    return counts


def _copy_assets(config: Config) -> tuple[Path, Path]:
    static_dir = Path(__file__).resolve().parent / "powerbi"
    theme_src = static_dir / "star_mart_theme.json"
    dax_src = static_dir / "measures.dax"
    for path in (theme_src, dax_src):
        if not path.exists():
            raise FileNotFoundError(f"缺少 Power BI 静态资源: {path}")

    out_root = config.path("powerbi")
    theme_dst = out_root / "theme" / "star_mart_theme.json"
    dax_dst = out_root / "measures.dax"
    theme_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(theme_src, theme_dst)
    shutil.copy2(dax_src, dax_dst)

    guide_src = config.root / "docs" / "powerbi.md"
    if guide_src.exists():
        shutil.copy2(guide_src, out_root / "README.md")
    return theme_dst, dax_dst


def export_powerbi(config: Config) -> dict:
    """生成 Power BI 可直接导入的星型数据集与配套资产。"""
    logger = get_logger()
    t0 = time.time()
    out_root = config.path("powerbi")
    data_dir = out_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Power BI 数据集导出: %s", out_root)
    counts = _build_dimensions(config, data_dir)
    counts.update(_build_facts(config, data_dir))
    theme_path, dax_path = _copy_assets(config)

    manifest = {
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
        "data_dir": str(data_dir),
        "row_counts": counts,
        "relationships": RELATIONSHIPS,
        "theme_file": str(theme_path),
        "measures_file": str(dax_path),
        "notes": [
            "dim_date 需在 Power BI 中标记为日期表，dt/date 列类型设为 Date。",
            "fact_operation_day 为公司级日汇总，fact_store_day 为门店级日汇总，勿在同一视觉对象中混用。",
            "fact_inventory_day、fact_store_day 中的 MTD/30 日指标为快照值，切片时取窗口最后一天。",
            "fact_retention 同时含 cohort_month 与 stat_month 两种月份角色，按需使用 USERELATIONSHIP。",
        ],
    }
    write_json(out_root / "_manifest.json", manifest)

    for name, rows in counts.items():
        logger.info("  %-24s %8d 行", name, rows)
    logger.info("Power BI 数据集完成: %d 张表，用时 %.1f 秒", len(counts), time.time() - t0)
    return counts


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    config = Config()
    config.ensure_dirs()
    setup_logger(config.path("run_log"))
    counts = export_powerbi(config)
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
