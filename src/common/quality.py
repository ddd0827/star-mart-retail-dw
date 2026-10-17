"""数据质量规则引擎。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml
from pyspark.sql import SparkSession

from .config import Config
from .logger import get_logger


class QualityError(RuntimeError):
    pass


class QualityRunner:
    def __init__(self, spark: SparkSession, config: Config, run_id: str):
        self.spark = spark
        self.config = config
        self.run_id = run_id
        self.logger = get_logger()
        rules_path = config.root / "config" / "quality_rules.yml"
        with open(rules_path, "r", encoding="utf-8") as f:
            self.rules = yaml.safe_load(f)["rules"]
        self.results: list[dict] = []

    def _run_rule(self, rule: dict, stage: str) -> dict:
        name = rule["name"]
        severity = rule.get("severity", "warning")
        table = rule.get("table", "")
        rule_type = rule.get("type", "sql")
        sql = rule["sql"]
        row = {
            "run_id": self.run_id,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stage": stage,
            "table": table,
            "rule": name,
            "severity": severity,
            "status": "PASS",
            "violations": 0,
            "threshold": rule.get("threshold", 0),
            "detail": "",
        }
        try:
            value = int(self.spark.sql(sql).first()[0] or 0)
            if rule_type == "min_rows":
                minimum = int(rule.get("min", 1))
                passed = value >= minimum
                row.update({
                    "violations": value,
                    "threshold": minimum,
                    "status": "PASS" if passed else ("FAIL" if severity == "critical" else "WARN"),
                    "detail": f"实际行数={value}, 最低要求={minimum}",
                })
            else:
                threshold = int(rule.get("threshold", 0))
                passed = value <= threshold
                row.update({
                    "violations": value,
                    "threshold": threshold,
                    "status": "PASS" if passed else ("FAIL" if severity == "critical" else "WARN"),
                    "detail": f"违规行数={value}, 容忍上限={threshold}",
                })
        except Exception as exc:  # noqa: BLE001
            row.update({
                "status": "ERROR",
                "detail": str(exc)[:500],
            })
            self.logger.error("质量规则执行失败 [%s]: %s", name, exc)
        return row

    def run_stage(self, stage: str) -> list[dict]:
        rules = [r for r in self.rules if r.get("stage") == stage]
        if not rules:
            return []
        self.logger.info("开始数据质量校验: stage=%s, 规则数=%d", stage, len(rules))
        stage_results = [self._run_rule(rule, stage) for rule in rules]
        self.results.extend(stage_results)
        failed = [r for r in stage_results if r["status"] in ("FAIL", "ERROR")]
        for r in stage_results:
            level = self.logger.info
            if r["status"] in ("FAIL", "ERROR"):
                level = self.logger.error
            elif r["status"] == "WARN":
                level = self.logger.warning
            level("  [%s] %s | %s | %s", r["status"], r["severity"], r["rule"], r["detail"])
        self.logger.info(
            "质量校验完成: stage=%s, 通过=%d, 失败/错误=%d",
            stage,
            len(stage_results) - len(failed),
            len(failed),
        )
        return stage_results

    def critical_failures(self) -> list[dict]:
        return [r for r in self.results if r["severity"] == "critical" and r["status"] in ("FAIL", "ERROR")]

    def assert_passed(self) -> None:
        failures = self.critical_failures()
        if failures and self.config.get("pipeline.fail_on_critical_dq", True):
            names = "；".join(f"{r['rule']}({r['detail']})" for r in failures[:5])
            raise QualityError(f"严重数据质量问题导致流程中止: {names}")

    def write_report(self, latest_name: str = "dq_report_latest.csv") -> Path:
        out_dir = self.config.path("quality")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"dq_report_{self.run_id}.csv"
        df = pd.DataFrame(self.results)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        latest = out_dir / latest_name
        df.to_csv(latest, index=False, encoding="utf-8-sig")
        self.logger.info("质量报告已写入: %s", path)
        return path
