$ErrorActionPreference = "Stop"

function Get-DevRepositoryRoot {
    Split-Path -Parent $PSScriptRoot
}

function Get-DevRuntimePaths {
    param([Parameter(Mandatory = $true)][string]$RepositoryRoot)

    $runtimeRoot = Join-Path $RepositoryRoot "tmp\dev"
    $logRoot = Join-Path $RepositoryRoot "logs\dev"
    [pscustomobject]@{
        RuntimeRoot = $runtimeRoot
        LogRoot = $logRoot
    }
}

function Initialize-DevRuntimePaths {
    param([Parameter(Mandatory = $true)][string]$RepositoryRoot)

    $paths = Get-DevRuntimePaths -RepositoryRoot $RepositoryRoot
    New-Item -ItemType Directory -Force -Path $paths.RuntimeRoot, $paths.LogRoot | Out-Null
    $paths
}

function Get-DevProcessRecordPath {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][ValidateSet("api", "web", "worker")][string]$Name
    )

    $paths = Get-DevRuntimePaths -RepositoryRoot $RepositoryRoot
    Join-Path $paths.RuntimeRoot "$Name.json"
}

function Get-DevProcessRecord {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][ValidateSet("api", "web", "worker")][string]$Name
    )

    $path = Get-DevProcessRecordPath -RepositoryRoot $RepositoryRoot -Name $Name
    if (-not (Test-Path -LiteralPath $path)) {
        return $null
    }
    try {
        Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
    } catch {
        Remove-Item -LiteralPath $path -Force
        return $null
    }
}

function Test-DevProcessRecord {
    param([Parameter(Mandatory = $true)]$Record)

    try {
        $process = Get-Process -Id ([int]$Record.ProcessId) -ErrorAction Stop
        $actualStart = $process.StartTime.ToUniversalTime().ToString("o")
        return $actualStart -eq [string]$Record.StartedAtUtc
    } catch {
        return $false
    }
}

function Set-DevProcessRecord {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][ValidateSet("api", "web", "worker")][string]$Name,
        [Parameter(Mandatory = $true)]$Process,
        [Parameter(Mandatory = $true)][string]$ScriptPath
    )

    $record = [ordered]@{
        ProcessId = $Process.Id
        StartedAtUtc = $Process.StartTime.ToUniversalTime().ToString("o")
        ScriptPath = $ScriptPath
    }
    $record | ConvertTo-Json | Set-Content -LiteralPath (Get-DevProcessRecordPath -RepositoryRoot $RepositoryRoot -Name $Name) -Encoding utf8
    [pscustomobject]$record
}

function Get-ProjectPortProcess {
    param(
        [Parameter(Mandatory = $true)][ValidateRange(1, 65535)][int]$Port,
        [Parameter(Mandatory = $true)][string]$RepositoryRoot
    )

    $listener = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($listener.Count -eq 0) {
        return $null
    }
    $repoPrefix = [regex]::Escape($RepositoryRoot)
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener[0].OwningProcess)" -ErrorAction SilentlyContinue
    if ($null -eq $candidate -or $candidate.CommandLine -notmatch $repoPrefix) {
        return $null
    }
    while ($candidate.ParentProcessId) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($candidate.ParentProcessId)" -ErrorAction SilentlyContinue
        if ($null -eq $parent -or $parent.CommandLine -notmatch $repoPrefix) {
            break
        }
        $candidate = $parent
    }
    Get-Process -Id $candidate.ProcessId -ErrorAction SilentlyContinue
}

function Stop-DevProcessTree {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        Stop-DevProcessTree -ProcessId $child.ProcessId
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Remove-StaleDevProcessRecord {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][ValidateSet("api", "web", "worker")][string]$Name
    )

    $record = Get-DevProcessRecord -RepositoryRoot $RepositoryRoot -Name $Name
    if ($null -ne $record -and -not (Test-DevProcessRecord -Record $record)) {
        Remove-Item -LiteralPath (Get-DevProcessRecordPath -RepositoryRoot $RepositoryRoot -Name $Name) -Force
        return $null
    }
    $record
}

function Test-LocalPortListening {
    param([Parameter(Mandatory = $true)][ValidateRange(1, 65535)][int]$Port)

    $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    # PowerShell 在没有结果时可能返回空数组而非 $null；空数组不能被视为端口已监听。
    return @($listeners).Count -gt 0
}

function Assert-DevCommand {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($null -eq (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "缺少命令 '$Name'。请安装后重试。"
    }
}

function Wait-ComposeServiceHealth {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string[]]$Services,
        [ValidateRange(5, 300)][int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastStates = @{}
    while ((Get-Date) -lt $deadline) {
        $allHealthy = $true
        foreach ($service in $Services) {
            $containerId = (& docker compose -f (Join-Path $RepositoryRoot "compose.yaml") ps -q $service).Trim()
            if (-not $containerId) {
                $lastStates[$service] = "container_missing"
                $allHealthy = $false
                continue
            }
            $state = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId).Trim()
            $lastStates[$service] = $state
            if ($state -ne "healthy") {
                $allHealthy = $false
            }
        }
        if ($allHealthy) {
            return
        }
        Start-Sleep -Seconds 2
    }
    $stateText = ($Services | ForEach-Object { "$_=$($lastStates[$_])" }) -join ", "
    throw "Docker 依赖在 $TimeoutSeconds 秒内未就绪：$stateText。可运行 'docker compose ps' 查看详情。"
}

function Start-ManagedDevProcess {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][ValidateSet("api", "web", "worker")][string]$Name,
        [Parameter(Mandatory = $true)][string]$ScriptPath
    )

    $paths = Initialize-DevRuntimePaths -RepositoryRoot $RepositoryRoot
    $recordPath = Get-DevProcessRecordPath -RepositoryRoot $RepositoryRoot -Name $Name
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $ScriptPath
    ) -WorkingDirectory $RepositoryRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $paths.LogRoot "$Name.out.log") -RedirectStandardError (Join-Path $paths.LogRoot "$Name.err.log") -PassThru
    Set-DevProcessRecord -RepositoryRoot $RepositoryRoot -Name $Name -Process $process -ScriptPath $ScriptPath
}

function Wait-LocalPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [ValidateRange(5, 180)][int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-LocalPortListening -Port $Port) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}
