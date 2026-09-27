[CmdletBinding()]
param(
    [ValidateRange(5, 300)][int]$DependencyTimeoutSeconds = 90,
    [ValidateRange(5, 180)][int]$ApplicationTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "dev-common.ps1")

$repoRoot = Get-DevRepositoryRoot
$envPath = Join-Path $repoRoot ".env"
$envTemplatePath = Join-Path $repoRoot ".env.example"

try {
    Assert-DevCommand -Name "docker"
    Assert-DevCommand -Name "python"
    Assert-DevCommand -Name "node"
    if ($null -eq (Get-Command "pnpm" -ErrorAction SilentlyContinue)) {
        Assert-DevCommand -Name "corepack"
    }

    if (-not (Test-Path -LiteralPath $envPath)) {
        Copy-Item -LiteralPath $envTemplatePath -Destination $envPath
        Write-Host "已从 .env.example 创建 .env；请按需修改本地密码。"
    }

    Initialize-DevRuntimePaths -RepositoryRoot $repoRoot | Out-Null
    Write-Host "正在启动 PostgreSQL、Redis 和 MinIO..."
    & docker compose -f (Join-Path $repoRoot "compose.yaml") up -d postgres redis minio
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose 启动失败。可运行 'docker compose ps' 查看详情。"
    }
    Wait-ComposeServiceHealth -RepositoryRoot $repoRoot -Services @("postgres", "redis", "minio") -TimeoutSeconds $DependencyTimeoutSeconds

    $services = @(
        [pscustomobject]@{ Name = "api"; Port = 8000; Script = (Join-Path $PSScriptRoot "dev-api.ps1") },
        [pscustomobject]@{ Name = "web"; Port = 3000; Script = (Join-Path $PSScriptRoot "dev-web.ps1") }
    )
    foreach ($service in $services) {
        $record = Remove-StaleDevProcessRecord -RepositoryRoot $repoRoot -Name $service.Name
        if (Test-LocalPortListening -Port $service.Port) {
            if ($null -ne $record) {
                Write-Host "$($service.Name) 已在运行，复用受管进程 PID $($record.ProcessId)。"
                continue
            }
            $projectProcess = Get-ProjectPortProcess -Port $service.Port -RepositoryRoot $repoRoot
            if ($null -ne $projectProcess) {
                $recovered = Set-DevProcessRecord -RepositoryRoot $repoRoot -Name $service.Name -Process $projectProcess -ScriptPath $service.Script
                Write-Host "$($service.Name) 已在运行，已重新接管项目进程 PID $($recovered.ProcessId)。"
                continue
            }
            throw "端口 $($service.Port) 已被未知进程占用；请先释放端口再运行。"
        }
        $started = Start-ManagedDevProcess -RepositoryRoot $repoRoot -Name $service.Name -ScriptPath $service.Script
        if (-not (Wait-LocalPort -Port $service.Port -TimeoutSeconds $ApplicationTimeoutSeconds)) {
            throw "$($service.Name) 未在 $ApplicationTimeoutSeconds 秒内监听端口 $($service.Port)。请查看 logs/dev/$($service.Name).err.log。"
        }
        Write-Host "$($service.Name) 已启动，PID $($started.ProcessId)。"
    }

    $worker = Remove-StaleDevProcessRecord -RepositoryRoot $repoRoot -Name "worker"
    if ($null -ne $worker) {
        Write-Host "worker 已在运行，复用受管进程 PID $($worker.ProcessId)。"
    } else {
        $started = Start-ManagedDevProcess -RepositoryRoot $repoRoot -Name "worker" -ScriptPath (Join-Path $PSScriptRoot "dev-worker.ps1")
        Write-Host "worker 已启动，PID $($started.ProcessId)。"
    }

    Write-Host "`n开发环境已就绪："
    Write-Host "  Web: http://localhost:3000"
    Write-Host "  API: http://localhost:8000/docs"
    Write-Host "  日志: logs/dev"
    Write-Host "  停止 API/Web/Worker: .\scripts\dev-stop.ps1"
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
