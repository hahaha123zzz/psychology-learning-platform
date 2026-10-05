param(
    [string]$SharedDoc = ".\STUDENT_DEMO_SHARED.md",
    [int]$IntervalSeconds = 60
)

if (-not (Test-Path $SharedDoc)) {
    Write-Error "Shared document not found: $SharedDoc"
    exit 1
}

$lastHash = (Get-FileHash $SharedDoc -Algorithm SHA256).Hash
Write-Host "Waiting for shared document changes: $SharedDoc"
Write-Host "Polling every $IntervalSeconds seconds..."

while ($true) {
    Start-Sleep -Seconds $IntervalSeconds

    if (-not (Test-Path $SharedDoc)) {
        Write-Warning "Shared document temporarily missing. Continue waiting."
        continue
    }

    $newHash = (Get-FileHash $SharedDoc -Algorithm SHA256).Hash

    if ($newHash -ne $lastHash) {
        Write-Host "Shared document changed."
        Write-Host "Latest events:"
        Get-Content $SharedDoc -Tail 80
        exit 0
    }
}
