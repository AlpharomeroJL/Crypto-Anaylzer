# Crypto-Analyzer: run commands using .venv (avoids ModuleNotFoundError).
# Doctor-first: runs crypto_analyzer.doctor before most commands unless -SkipDoctor is passed.
# Must run from repo root, or script will cd to repo root (parent of scripts/).
# Usage: .\scripts\run.ps1 [-SkipDoctor] <command> [args...]
# Commands: poll, universe-poll, materialize, report, reportv2, streamlit, doctor, test
param(
    [switch]$SkipDoctor,
    [Parameter(Position = 0)]$Command,
    [Parameter(ValueFromRemainingArguments = $true)]$Passthrough
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Venv not found at $py. Create it: python -m venv .venv; .\.venv\Scripts\Activate; pip install -r requirements.txt"
    exit 1
}
Set-Location $root

# Strip -SkipDoctor from passthrough so it isn't passed to Python
$filtered = @()
if ($Passthrough) {
    foreach ($p in $Passthrough) {
        if ($p -ne '-SkipDoctor') { $filtered += $p }
        else { $SkipDoctor = $true }
    }
}

$runDoctorFirst = $false
if ($Command -and $Command -ne 'doctor' -and $Command -ne 'test' -and (-not $SkipDoctor)) {
    $runDoctorFirst = $true
}

if ($runDoctorFirst) {
    $doctorExit = 0
    & $py -m crypto_analyzer.doctor
    $doctorExit = $LASTEXITCODE
    if ($doctorExit -ne 0) {
        exit $doctorExit
    }
}

switch ($Command) {
    "poll"           { & $py cli/poll.py --interval 60 @filtered; exit $LASTEXITCODE }
    "universe-poll"  { & $py cli/poll.py --universe @filtered; exit $LASTEXITCODE }
    "materialize"    { & $py cli/materialize.py @filtered; exit $LASTEXITCODE }
    "analyze"        { & $py cli/analyze.py @filtered; exit $LASTEXITCODE }
    "scan"           { & $py cli/scan.py @filtered; exit $LASTEXITCODE }
    "report"         { & $py cli/research_report.py @filtered; exit $LASTEXITCODE }
    "reportv2"       { & $py cli/research_report_v2.py @filtered; exit $LASTEXITCODE }
    "daily"          { & $py cli/report_daily.py @filtered; exit $LASTEXITCODE }
    "backtest"       { & $py cli/backtest.py @filtered; exit $LASTEXITCODE }
    "walkforward"    { & $py cli/backtest_walkforward.py @filtered; exit $LASTEXITCODE }
    "streamlit"      { & $py -m streamlit run cli/app.py @filtered; exit $LASTEXITCODE }
    "api"            { & $py cli/api.py @filtered; exit $LASTEXITCODE }
    "doctor"         { & $py -m crypto_analyzer.doctor @filtered; exit $LASTEXITCODE }
    "test"           { & $py -m pytest tests/ @filtered; exit $LASTEXITCODE }
    default          {
        if ($Command) { & $py $Command @filtered; exit $LASTEXITCODE } else {
            Write-Host "Usage: .\scripts\run.ps1 [-SkipDoctor] <command> [args...]"
            Write-Host "Commands: poll, universe-poll, materialize, analyze, scan, report, reportv2,"
            Write-Host "          daily, backtest, walkforward, streamlit, api, doctor, test"
            Write-Host "  -SkipDoctor  Skip pre-flight doctor (default: run doctor before most commands)"
            exit 1
        }
    }
}
