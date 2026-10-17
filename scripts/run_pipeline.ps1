$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "未找到 .venv，请先运行 scripts\setup_env.ps1"
}
& $python -m src.etl.pipeline @args
