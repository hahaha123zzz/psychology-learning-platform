$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "dev-common.ps1")

$repoRoot = Get-DevRepositoryRoot
foreach ($name in @("api", "web", "worker")) {
    $recordPath = Get-DevProcessRecordPath -RepositoryRoot $repoRoot -Name $name
    $record = Get-DevProcessRecord -RepositoryRoot $repoRoot -Name $name
    if ($null -eq $record) {
        Write-Host "$name 没有受管运行进程。"
        continue
    }
    if (-not (Test-DevProcessRecord -Record $record)) {
        Remove-Item -LiteralPath $recordPath -Force
        Write-Host "$name 的 PID 记录已过期，未停止任何进程。"
        continue
    }
    Stop-Process -Id ([int]$record.ProcessId) -Force
    Remove-Item -LiteralPath $recordPath -Force
    Write-Host "$name 已停止。"
}
Write-Host "Docker 依赖仍在运行；如需手动停止，请执行 'docker compose stop'。"
