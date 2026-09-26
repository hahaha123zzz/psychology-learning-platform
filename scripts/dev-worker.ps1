$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serverRoot = Join-Path $repoRoot "server"
$venvPython = Join-Path $serverRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "未找到 server\.venv；请先运行 .\scripts\dev.ps1。"
}

Push-Location $serverRoot
try {
    # Windows 不支持 prefork；solo 仍可提供独立、可重启的持久任务进程。
    & $venvPython -m celery -A app.core.celery_app worker --loglevel=INFO --pool=solo
} finally {
    Pop-Location
}
