param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("root", "a", "b", "c")]
    [string]$Window,
    [switch]$Snapshot,
    [ValidatePattern("^[a-zA-Z0-9-]{1,40}$")]
    [string]$SnapshotName
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "web"
$runtimeParent = Join-Path $webRoot ".r2-runtime"
$runtimeName = if ($Snapshot) {
    if ([string]::IsNullOrWhiteSpace($SnapshotName)) { "r2-$Window-snapshot" } else { $SnapshotName }
} else {
    "r2-$Window"
}
$runtimeRoot = Join-Path $runtimeParent $runtimeName

if (-not (Test-Path -LiteralPath $webRoot -PathType Container)) {
    throw "Web 根目录不存在：$webRoot"
}
if (Test-Path -LiteralPath $runtimeRoot) {
    throw "隔离运行目录已存在；为保护既有数据，不会覆盖或清理：$runtimeRoot"
}

New-Item -ItemType Directory -Path $runtimeRoot | Out-Null
foreach ($name in @("app", "components", "lib", "public", "design-system", "node_modules")) {
    $source = Join-Path $webRoot $name
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        continue
    }
    $destination = Join-Path $runtimeRoot $name
    if ($Snapshot -and $name -ne "node_modules") {
        Copy-Item -LiteralPath $source -Destination $destination -Recurse
    } else {
        New-Item -ItemType Junction -Path $destination -Target $source | Out-Null
    }
}

foreach ($name in @("package.json", "next.config.ts", "tsconfig.json", "postcss.config.mjs", "eslint.config.mjs")) {
    $source = Join-Path $webRoot $name
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $runtimeRoot $name)
    }
}

Write-Output "隔离 Next 项目已准备：$runtimeRoot"
if ($Snapshot) {
    Write-Output "业务源代码已复制为验收快照；仅 node_modules 使用 junction，Next 生成文件与构建产物均隔离。"
} else {
    Write-Output "源代码目录使用 junction；若 Turbopack 无法发现路由，请改用 -Snapshot 快照模式。"
}
