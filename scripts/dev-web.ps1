$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "web"

function Invoke-ProjectPnpm {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $pnpm = Get-Command "pnpm" -ErrorAction SilentlyContinue
    if ($null -ne $pnpm) {
        & $pnpm.Source @Arguments
    } else {
        $corepack = Get-Command "corepack" -ErrorAction SilentlyContinue
        if ($null -eq $corepack) {
            throw "缺少 pnpm，且 Node.js 未提供 corepack。请安装 Node.js LTS 后重试。"
        }
        $env:COREPACK_HOME = Join-Path $repoRoot "tmp\corepack"
        New-Item -ItemType Directory -Force -Path $env:COREPACK_HOME | Out-Null
        & $corepack.Source pnpm @Arguments
    }
    if ($LASTEXITCODE -ne 0) {
        throw "pnpm $($Arguments -join ' ') 执行失败。请查看以上输出。"
    }
}

Push-Location $webRoot
try {
    if (-not (Test-Path -LiteralPath (Join-Path $webRoot "node_modules"))) {
        Invoke-ProjectPnpm -Arguments @("install")
    }
    Invoke-ProjectPnpm -Arguments @("dev")
} finally {
    Pop-Location
}
