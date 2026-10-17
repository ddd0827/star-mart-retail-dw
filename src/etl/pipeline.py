"""数仓总调度：ODS -> DIM -> DWD -> DWS -> ADS -> 质量 -> 导出 -> 看板。

用法：
    .venv\\Scripts\\python.exe -m src.etl.pipeline --mode full
    .venv\\Scripts\\python.exe -m src.etl.pipeline --mode daily --date 2026-10-16
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common.config import Config
from src.common.io_utils import write_json
from src.common.logger import get_logger, setup_logger
from src.common.quality import QualityRunner
from src.common.spark_session import get_spark
from src.etl.ads import run_ads
from src.etl.dim import run_dim
from src.etl.dwd import run_dwd
from src.etl.dws import run_dws
from src.etl.ods import run_ods


def parse_args() -> argparse.Namespace:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="星选生活连锁零售数仓调度")
    parser.add_argument("--mode", choices=["full", "daily"], default="full")
    parser.add_argument("--date", help="daily 模式目标日期 YYYY-MM-DD")
    parser.add_argument("--start-date", help="full 模式开始日期")
    parser.add_argument("--end-date", help="full 模式结束日期")
    parser.add_argument("--lookback-days", type=int, default=None, help="daily 模式回溯天数")
    parser.add_argument("--skip-quality", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--skip-dashboard", action="store_true")
    return parser.parse_args()


def build_configs(args: argparse.Namespace) -> tuple[Config, Config, Config, str]:
    overrides = {}
    if args.mode == "full":
        dates = {}
        if args.start_date:
            dates["start"] = args.start_date
        if args.end_date:
            dates["end"] = args.end_date
        if dates:
            overrides["dates"] = dates
    base = Config(overrides=overrides or None)
    if args.mode == "full":
        return base, base, base, base.start_date.isoformat()

    target = date.fromisoformat(args.date) if args.date else base.end_date
    lookback = args.lookback_days or int(base.get("pipeline.lookback_days_daily", 21))
    if lookback < 1:
        raise ValueError("回溯天数必须大于 0")
    proc_start = max(base.start_date, target - timedelta(days=lookback - 1))
    proc = base.with_overrides({"dates": {"start": proc_start.isoformat(), "end": target.isoformat()}})
    # 退款最长延迟 14 天：DWD 需要额外读取更早的订单，才能把退款挂回原订单行；
    # 输出层（DWS/ADS）仍然只重算 proc 窗口。
    input_start = max(base.start_date, proc.start_date - timedelta(days=14))
    input_cfg = base.with_overrides({"dates": {"start": input_start.isoformat(), "end": target.isoformat()}})
    return base, proc, input_cfg, base.start_date.isoformat()


def main() -> int:
    args = parse_args()
    base_config, proc_config, input_config, history_start = build_configs(args)
    base_config.ensure_dirs()
    proc_config.ensure_dirs()
    logger = setup_logger(proc_config.path("run_log"))
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("=" * 78)
    logger.info("数仓调度开始: mode=%s, 输出范围=%s ~ %s, DWD输入范围=%s ~ %s, history_start=%s",
                args.mode, proc_config.start_date, proc_config.end_date,
                input_config.start_date, input_config.end_date, history_start)
    logger.info("Run ID: %s", run_id)

    spark = get_spark(proc_config, f"retail_dw_{args.mode}")
    quality = QualityRunner(spark, proc_config, run_id)
    stages: list[dict] = []
    status = "SUCCESS"
    error_message = ""
    t_all = time.time()

    def stage(name: str, func):
        t = time.time()
        logger.info("-" * 78)
        logger.info("阶段开始: %s", name)
        try:
            result = func()
            elapsed = round(time.time() - t, 2)
            stages.append({"stage": name, "status": "SUCCESS", "seconds": elapsed,
                           "result": result if isinstance(result, dict) else {}})
            logger.info("阶段完成: %s，用时 %.1f 秒", name, elapsed)
            return result
        except Exception as exc:
            elapsed = round(time.time() - t, 2)
            stages.append({"stage": name, "status": "FAILED", "seconds": elapsed, "error": str(exc)[:1000]})
            logger.error("阶段失败: %s | %s", name, exc)
            raise

    try:
        stage("ODS", lambda: run_ods(spark, input_config))
        stage("DIM", lambda: run_dim(spark, proc_config))
        stage("DWD", lambda: run_dwd(spark, input_config))
        if not args.skip_quality:
            logger.info("-" * 78)
            logger.info("阶段开始: DQ-DWD")
            quality.run_stage("dwd")
            quality.assert_passed()

        stage("DWS", lambda: run_dws(spark, proc_config))
        if not args.skip_quality:
            logger.info("阶段开始: DQ-DWS")
            quality.run_stage("dws")
            quality.assert_passed()

        stage("ADS", lambda: run_ads(
            spark, proc_config,
            history_start=history_start,
            output_start=proc_config.start_date.isoformat(),
            output_end=proc_config.end_date.isoformat(),
        ))
        if not args.skip_quality:
            logger.info("阶段开始: DQ-ADS")
            quality.run_stage("ads")
            quality.assert_passed()

        if not args.skip_export:
            from src.report.export import export_ads
            stage("EXPORT", lambda: export_ads(spark, base_config))

        if not args.skip_dashboard:
            from src.report.dashboard import build_dashboard
            stage("DASHBOARD", lambda: {"dashboard": str(build_dashboard(base_config))})

    except Exception as exc:  # noqa: BLE001
        status = "FAILED"
        error_message = str(exc)
        logger.error("调度失败: %s", exc)
        logger.error(traceback.format_exc())
    finally:
        if not args.skip_quality:
            try:
                quality.write_report("dq_report_latest.csv" if args.mode == "full" else "dq_report_latest_daily.csv")
            except Exception as exc:  # noqa: BLE001
                logger.warning("质量报告写入失败: %s", exc)
        total = round(time.time() - t_all, 2)
        summary = {
            "run_id": run_id,
            "mode": args.mode,
            "status": status,
            "error": error_message,
            "start_date": proc_config.start_date.isoformat(),
            "end_date": proc_config.end_date.isoformat(),
            "dwd_input_start": input_config.start_date.isoformat(),
            "total_seconds": total,
            "stages": stages,
            "dq": {
                "total": len(quality.results),
                "critical_failures": len(quality.critical_failures()),
                "failed_or_warn": sum(1 for r in quality.results if r["status"] != "PASS"),
            },
        }
        out = proc_config.path("run_log") / f"etl_run_{run_id}.json"
        write_json(out, summary)
        latest_name = "etl_run_latest.json" if args.mode == "full" else "etl_run_latest_daily.json"
        write_json(proc_config.path("run_log") / latest_name, summary)
        logger.info("=" * 78)
        logger.info("数仓调度结束: %s，总用时 %.1f 秒", status, total)
        logger.info("运行日志: %s", out)
        spark.stop()
    return 0 if status == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
