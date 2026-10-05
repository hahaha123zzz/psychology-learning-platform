param(
    [Parameter(Mandatory = $false)]
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$statePath = "docs/v1/V1并行启动状态.md"
$excludedPrefixes = @(".pnpm-store/")

$start = [System.Diagnostics.ProcessStartInfo]::new()
$start.FileName = "git"
$start.Arguments = "status --porcelain=v1 -z --untracked-files=all"
$start.WorkingDirectory = $repoRoot
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $start
if (-not $process.Start()) {
    throw "无法启动 git status。"
}
$memory = [System.IO.MemoryStream]::new()
$process.StandardOutput.BaseStream.CopyTo($memory)
$process.WaitForExit()
if ($process.ExitCode -ne 0) {
    throw "git status 失败：$($process.StandardError.ReadToEnd())"
}

$bytes = $memory.ToArray()
$records = [System.Collections.Generic.SortedDictionary[string, string]]::new(
    [System.StringComparer]::Ordinal
)
$offset = 0
while ($offset -lt $bytes.Length) {
    $end = [Array]::IndexOf($bytes, [byte]0, $offset)
    if ($end -lt 0) { $end = $bytes.Length }
    if ($end -eq $offset) {
        $offset++
        continue
    }
    $record = [System.Text.Encoding]::UTF8.GetString($bytes, $offset, $end - $offset)
    $offset = $end + 1
    if ($record.Length -lt 4) { continue }

    $status = $record.Substring(0, 2)
    $relativePath = $record.Substring(3).Replace("\", "/")
    if (($status.Contains("R") -or $status.Contains("C")) -and $offset -lt $bytes.Length) {
        $oldEnd = [Array]::IndexOf($bytes, [byte]0, $offset)
        if ($oldEnd -lt 0) { $oldEnd = $bytes.Length }
        $offset = $oldEnd + 1
    }
    if ($relativePath -eq $statePath) { continue }
    if ($excludedPrefixes | Where-Object { $relativePath.StartsWith($_, [StringComparison]::Ordinal) }) {
        continue
    }

    $fullPath = Join-Path $repoRoot $relativePath.Replace("/", [IO.Path]::DirectorySeparatorChar)
    $fileHash = "<deleted>"
    if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
        $fileHash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToUpperInvariant()
    }
    elseif (Test-Path -LiteralPath $fullPath -PathType Container) {
        throw "Git 状态中的路径不是文件（请检查是否为子模块或路径编码问题）：$relativePath"
    }
    $records.Add($relativePath, "$status`t$fileHash`t$relativePath")
}

$payload = [string]::Join("`n", @($records.Values))
$payloadBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($payload)
$fingerprint = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($payloadBytes))
$head = (& git -C $repoRoot rev-parse HEAD).Trim()

if (-not $Quiet) {
    [pscustomobject]@{
        Head = $head
        IncludedEntries = $records.Count
        Excluded = "$statePath (self-reference), .pnpm-store/ (ephemeral cache)"
        Fingerprint = $fingerprint
    } | Format-List
}
