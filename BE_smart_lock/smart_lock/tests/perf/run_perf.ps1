# Performance test runner for Windows PowerShell.
#
# Usage:
#   cd BE_smart_lock\smart_lock
#   .\venv\Scripts\Activate.ps1
#   .\tests\perf\run_perf.ps1                       # default: 10 / 50 / 100 concurrency, 2m each
#   .\tests\perf\run_perf.ps1 -Duration 3m          # 3 minutes per stage
#   .\tests\perf\run_perf.ps1 -HostUrl http://192.168.1.10:8000
#   .\tests\perf\run_perf.ps1 -LoginOnly            # focus on POST /api/login
#   .\tests\perf\run_perf.ps1 -SkipPrepare          # skip prepare_data.py
#
# Outputs (under tests\perf\results\):
#   c<N>_stats.csv          per-endpoint aggregate for that stage
#   c<N>_stats_history.csv  time-series data
#   c<N>_failures.csv       failure detail
#   c<N>.html               Locust HTML report (screenshot-ready)

param(
    [string]$HostUrl = "http://localhost:8000",
    [string]$Duration = "2m",
    [int[]]$Concurrencies = @(10, 50, 100),
    [int]$SpawnRate = 20,
    [switch]$SkipPrepare,
    [switch]$LoginOnly
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$resultsDir = Join-Path $scriptDir "results"

if (-not (Test-Path $resultsDir)) {
    New-Item -ItemType Directory -Path $resultsDir | Out-Null
}

if (-not $SkipPrepare) {
    Write-Host "[perf] preparing test accounts ..." -ForegroundColor Cyan
    python (Join-Path $scriptDir "prepare_data.py")
    if ($LASTEXITCODE -ne 0) { throw "prepare_data.py failed" }
}

$userClass = ""
$labelSuffix = ""
if ($LoginOnly) {
    $userClass = "LoginOnlyUser"
    $labelSuffix = "_login"
}

foreach ($c in $Concurrencies) {
    $label = "c${c}${labelSuffix}"
    $csvPrefix = Join-Path $resultsDir $label
    $htmlPath = Join-Path $resultsDir ($label + ".html")

    Write-Host ""
    Write-Host "==== stage: concurrency=$c duration=$Duration ====" -ForegroundColor Yellow
    $locustArgs = @(
        "-f", (Join-Path $scriptDir "locustfile.py"),
        "--headless",
        "-u", $c,
        "-r", $SpawnRate,
        "-t", $Duration,
        "--host", $HostUrl,
        "--csv", $csvPrefix,
        "--html", $htmlPath,
        "--only-summary"
    )
    if ($userClass) { $locustArgs += $userClass }

    & locust @locustArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "locust returned non-zero, continuing to next stage"
    }
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "[perf] all stages finished. results dir: $resultsDir" -ForegroundColor Green
Write-Host "[perf] next step: python tests\perf\aggregate_results.py"
