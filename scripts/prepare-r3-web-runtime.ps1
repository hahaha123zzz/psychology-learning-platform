param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("a", "b", "c", "d", "e", "f", "g")]
    [string]$Window,

    [Parameter(Mandatory = $false)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string]$SnapshotName
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "web"
$runtimeParent = Join-Path $webRoot ".r3-runtime"
if ([string]::IsNullOrWhiteSpace($SnapshotName)) {
    $SnapshotName = "r3-$Window-snapshot"
}
$runtimeRoot = Join-Path $runtimeParent $SnapshotName

if (-not (Test-Path -LiteralPath $webRoot -PathType Container)) {
    throw "Web 根目录不存在：$webRoot"
}
if (Test-Path -LiteralPath $runtimeRoot) {
    throw "隔离运行目录已存在；为保护既有数据，不会覆盖或清理：$runtimeRoot"
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
foreach ($name in @("app", "components", "lib", "public", "design-system", "tests")) {
    $source = Join-Path $webRoot $name
    if (Test-Path -LiteralPath $source -PathType Container) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $runtimeRoot $name) -Recurse
    }
}

$nodeModules = Join-Path $webRoot "node_modules"
if (Test-Path -LiteralPath $nodeModules -PathType Container) {
    New-Item -ItemType Junction -Path (Join-Path $runtimeRoot "node_modules") -Target $nodeModules | Out-Null
}

foreach ($name in @("package.json", "next.config.ts", "tsconfig.json", "postcss.config.mjs", "eslint.config.mjs")) {
    $source = Join-Path $webRoot $name
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $runtimeRoot $name)
    }
}

Write-Output "R3 隔离 Next 源码快照已准备：$runtimeRoot"
Write-Output "业务源代码、测试和配置均为物理副本；仅 node_modules 使用 junction。"
