$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "web"

Push-Location $webRoot
try {
    if (-not (Test-Path -LiteralPath (Join-Path $webRoot "node_modules"))) {
        pnpm install
    }
    pnpm dev
} finally {
    Pop-Location
}

