$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serverRoot = Join-Path $repoRoot "server"
$venvPython = Join-Path $serverRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $serverRoot ".venv")
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -e "${serverRoot}[dev]"
}

Push-Location $serverRoot
try {
    & $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
} finally {
    Pop-Location
}
