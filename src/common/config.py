"""项目配置加载。"""
from __future__ import annotations

import copy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from .env import project_root


class Config:
    def __init__(self, path: str | Path | None = None, overrides: dict[str, Any] | None = None):
        self.root = project_root()
        self.config_path = Path(path) if path else self.root / "config" / "project.yml"
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.data = yaml.safe_load(f)
        if overrides:
            self._deep_update(self.data, overrides)
        self.project = self.data["project"]
        self.scale = self.data["scale"]
        self.dates_cfg = self.data["dates"]
        self.start_date = date.fromisoformat(str(self.dates_cfg["start"]))
        self.end_date = date.fromisoformat(str(self.dates_cfg["end"]))
        if self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        self.seed = int(self.project["seed"])

    @staticmethod
    def _deep_update(base: dict, override: dict) -> dict:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                Config._deep_update(base[key], value)
            else:
                base[key] = value
        return base

    def with_overrides(self, overrides: dict[str, Any]) -> "Config":
        new = copy.deepcopy(self)
        new._deep_update(new.data, overrides)
        new.scale = new.data["scale"]
        new.dates_cfg = new.data["dates"]
        new.start_date = date.fromisoformat(str(new.dates_cfg["start"]))
        new.end_date = date.fromisoformat(str(new.dates_cfg["end"]))
        new.seed = int(new.project["seed"])
        return new

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def path(self, key: str) -> Path:
        value = self.data["paths"][key]
        p = Path(value)
        return p if p.is_absolute() else self.root / p

    def ensure_dirs(self) -> None:
        for key in ("raw", "warehouse", "output", "ads_export", "quality", "run_log",
                    "dashboard_assets", "powerbi", "tmp"):
            self.path(key).mkdir(parents=True, exist_ok=True)
        for layer in ("ods", "dim", "dwd", "dws", "ads"):
            (self.path("warehouse") / layer).mkdir(parents=True, exist_ok=True)

    def date_list(self) -> list[date]:
        days = (self.end_date - self.start_date).days + 1
        return [self.start_date + timedelta(days=i) for i in range(days)]

    def dt_list(self) -> list[str]:
        return [d.isoformat() for d in self.date_list()]

    @property
    def spark_cfg(self) -> dict:
        return self.data["spark"]
