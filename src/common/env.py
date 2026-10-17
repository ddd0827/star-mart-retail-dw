"""项目内环境变量配置。

必须在 import pyspark 之前调用 configure_environment()，保证 JVM
使用项目自带的 JDK 17 与 Hadoop winutils，而不是依赖系统环境。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def configure_environment() -> Path:
    root = project_root()
    java_home = root / "env" / "jdk17"
    hadoop_home = root / "env" / "hadoop"
    tmp_dir = root / "tmp"
    for path in (tmp_dir / "spark", tmp_dir / "tmp"):
        path.mkdir(parents=True, exist_ok=True)

    if not (java_home / "bin" / "java.exe").exists():
        raise RuntimeError(
            f"未找到项目内 JDK：{java_home}\n"
            "请先运行 scripts/setup_env.ps1 或 python scripts/setup_env.py"
        )

    os.environ["JAVA_HOME"] = str(java_home)
    os.environ["HADOOP_HOME"] = str(hadoop_home)
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    os.environ["SPARK_LOCAL_IP"] = "127.0.0.1"
    os.environ["PYTHONUTF8"] = "1"
    os.environ["TEMP"] = str(tmp_dir / "tmp")
    os.environ["TMP"] = str(tmp_dir / "tmp")

    prefix = [str(java_home / "bin"), str(hadoop_home / "bin")]
    current = os.environ.get("PATH", "")
    parts = [p for p in current.split(os.pathsep) if p]
    os.environ["PATH"] = os.pathsep.join(prefix + [p for p in parts if p not in prefix])

    # 让 JVM 能加载 hadoop.dll；PATH 之外的保险。
    java_opts = os.environ.get("JAVA_TOOL_OPTIONS", "")
    lib_opt = f"-Djava.library.path={hadoop_home / 'bin'}"
    if "-Djava.library.path" not in java_opts:
        os.environ["JAVA_TOOL_OPTIONS"] = (java_opts + " " + lib_opt).strip()
    return root
