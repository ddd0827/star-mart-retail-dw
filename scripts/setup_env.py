"""一键安装项目内运行环境（Windows）。

- .venv 虚拟环境与 Python 依赖
- 免安装 JDK 17（项目内，不修改系统环境变量）
- Hadoop winutils.exe / hadoop.dll（本地 Spark 文件系统兼容）

用法（项目根目录）：
    python scripts/setup_env.py
"""
from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
ENV_DIR = ROOT / "env"
JDK_DIR = ENV_DIR / "jdk17"
HADOOP_BIN = ENV_DIR / "hadoop" / "bin"
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"

JDK_URLS = [
    "https://aka.ms/download-jdk/microsoft-jdk-17-windows-x64.zip",
    "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse",
]
WINUTILS_FILES = {
    "winutils.exe": "496a591eb1e67df2a620f710d529ba6ddfe1c19149e6647cc4e320bb0efd8553",
    "hadoop.dll": "d7ab36a68518748cef142be2da5069b4c763c2cd764c1d2e6ac48c7200405be3",
}


def log(message: str) -> None:
    print(f"[setup] {message}", flush=True)


def download(url: str, target: Path) -> None:
    log(f"下载 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "star-mart-dw-setup/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response, open(target, "wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)


def ensure_venv() -> Path:
    if not (VENV_DIR / "Scripts" / "python.exe").exists():
        log("创建 .venv 虚拟环境")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
    return VENV_DIR / "Scripts" / "python.exe"


def ensure_jdk() -> None:
    if (JDK_DIR / "bin" / "java.exe").exists():
        log("JDK 17 已存在，跳过")
        return
    ENV_DIR.mkdir(parents=True, exist_ok=True)
    archive = ENV_DIR / "jdk17.zip"
    last_error = None
    for url in JDK_URLS:
        try:
            download(url, archive)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log(f"下载失败，尝试下一个镜像: {exc}")
    if not archive.exists():
        raise RuntimeError(f"JDK 下载失败: {last_error}")
    log("解压 JDK")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(ENV_DIR)
    candidates = [p for p in ENV_DIR.glob("jdk-*") if p.is_dir()]
    if not candidates:
        raise RuntimeError("解压后未找到 JDK 目录")
    candidates[0].rename(JDK_DIR)
    archive.unlink(missing_ok=True)
    log("JDK 安装完成")


def ensure_winutils() -> None:
    HADOOP_BIN.mkdir(parents=True, exist_ok=True)
    for name, expected_sha in WINUTILS_FILES.items():
        target = HADOOP_BIN / name
        if target.exists():
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if digest == expected_sha:
                log(f"{name} 已存在，校验通过")
                continue
            target.unlink()
        url = f"https://api.github.com/repos/cdarlint/winutils/contents/hadoop-3.3.6/bin/{name}?ref=master"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github.raw",
            "User-Agent": "star-mart-dw-setup/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()
            target.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            if digest != expected_sha:
                target.unlink(missing_ok=True)
                raise RuntimeError(f"{name} SHA256 校验失败: {digest}")
            log(f"{name} 下载并校验完成")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"{name} 下载失败: {exc}\n"
                "如网络受限，可手动下载 cdarlint/winutils 的 hadoop-3.3.6/bin 文件放入 env/hadoop/bin"
            ) from exc


def ensure_python_deps(python_exe: Path) -> None:
    log("安装 Python 依赖（PySpark 约 318MB，首次安装需要几分钟）")
    subprocess.check_call([str(python_exe), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    subprocess.check_call([str(python_exe), "-m", "pip", "install", "-r", str(REQUIREMENTS)])


def smoke_test(python_exe: Path) -> None:
    log("运行 Spark Parquet 读写冒烟测试")
    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "from src.common.config import Config;"
        "from src.common.spark_session import get_spark;"
        "cfg=Config(); spark=get_spark(cfg,'setup-smoke');"
        "p=(cfg.root/'tmp'/'setup_smoke').as_posix();"
        "spark.createDataFrame([(1,'测试')],['id','name']).write.mode('overwrite').parquet(p);"
        "print('SMOKE', spark.read.parquet(p).count());"
        "spark.stop()" % str(ROOT)
    )
    subprocess.check_call([str(python_exe), "-c", code])


def main() -> int:
    if platform.system() != "Windows":
        log("当前脚本主要面向 Windows；Linux/macOS 请使用对应 JDK 与 Spark 部署方式")
    log(f"项目目录: {ROOT}")
    ensure_jdk()
    ensure_winutils()
    python_exe = ensure_venv()
    ensure_python_deps(python_exe)
    smoke_test(python_exe)
    log("环境安装完成。")
    log("生成数据: .venv\\Scripts\\python.exe -m src.generator.generate")
    log("运行数仓: .venv\\Scripts\\python.exe -m src.etl.pipeline --mode full")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
