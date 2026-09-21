$common = Join-Path (Split-Path -Parent $PSScriptRoot) "dev-common.ps1"
. $common

Describe "开发启动公共函数" {
    $testRoot = Join-Path $TestDrive "project"
    New-Item -ItemType Directory -Path $testRoot | Out-Null

    It "将运行记录和日志隔离在仓库内" {
        $paths = Get-DevRuntimePaths -RepositoryRoot $testRoot
        $paths.RuntimeRoot | Should Be (Join-Path $testRoot "tmp\dev")
        $paths.LogRoot | Should Be (Join-Path $testRoot "logs\dev")
    }

    It "按服务名生成独立 PID 记录" {
        (Get-DevProcessRecordPath -RepositoryRoot $testRoot -Name "api") | Should Match "api\.json$"
        (Get-DevProcessRecordPath -RepositoryRoot $testRoot -Name "web") | Should Match "web\.json$"
    }

    It "拒绝不匹配当前进程启动时间的 PID 记录" {
        $record = [pscustomobject]@{
            ProcessId = $PID
            StartedAtUtc = "2000-01-01T00:00:00.0000000Z"
        }
        (Test-DevProcessRecord -Record $record) | Should Be $false
    }

    It "仅接受合法本地端口" {
        foreach ($port in @(0, 65536)) {
            $caught = $null
            try {
                Test-LocalPortListening -Port $port | Out-Null
            } catch {
                $caught = $_
            }
            $caught | Should Not BeNullOrEmpty
            $caught.Exception.GetType().FullName | Should Be "System.Management.Automation.ParameterBindingValidationException"
        }
    }
}
