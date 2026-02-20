# Crypto-Analyzer: run commands using .venv (avoids ModuleNotFoundError).
# Doctor-first: runs crypto_analyzer.doctor before most commands unless -SkipDoctor is passed.
# Must run from repo root, or script will cd to repo root (parent of scripts/).
# Usage: .\scripts\run.ps1 [-SkipDoctor] <command> [args...]
# Commands: poll, universe-poll, materialize, report, reportv2, streamlit, doctor, test, demo, check-dataset
param(
    [switch]$SkipDoctor,
    [Parameter(Position = 0)]$Command,
    [Parameter(ValueFromRemainingArguments = $true)]$Passthrough
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Venv not found at $py. Create it: python -m venv .venv; .\.venv\Scripts\Activate; .\.venv\Scripts\python.exe -m pip install -e `".[dev]`""
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
if ($Command -and $Command -ne 'doctor' -and $Command -ne 'test' -and $Command -ne 'demo' -and $Command -ne 'verify' -and (-not $SkipDoctor)) {
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
    "demo"           { & $py cli/demo.py @filtered; exit $LASTEXITCODE }
    "check-dataset"  { & $py tools/check_dataset.py @filtered; exit $LASTEXITCODE }
    "null_suite"     { & $py cli/null_suite.py @filtered; exit $LASTEXITCODE }
    "promotion"      { & $py cli/promotion.py @filtered; exit $LASTEXITCODE }
    "verify"         {
        Write-Host "== verify: doctor -> pytest -> ruff -> research-only -> diagrams =="
        Write-Host "OS:        $(& $py -c "import platform; print(platform.platform())" 2>&1)"
        Write-Host "Python:    $(& $py -c "import sys; print(sys.version.replace(chr(10),' '))" 2>&1)"
        Write-Host "Executable: $(& $py -c "import sys; print(sys.executable)" 2>&1)"
        Write-Host "Pytest:    $(& $py -m pytest --version 2>&1)"
        Write-Host "Ruff:      $(& $py -m ruff --version 2>&1)"
        $totalSw = [System.Diagnostics.Stopwatch]::StartNew()
        $stepLabelWidth = 14
        function _StepPass { param([string]$Label, [double]$Sec) Write-Host ("[PASS] " + $Label.PadRight($stepLabelWidth) + " ($([math]::Round($Sec, 2))s)") }
        function _StepFail { param([string]$Label, [string]$Detail) Write-Host ("[FAIL] " + $Label.PadRight($stepLabelWidth) + " $Detail") }
        function _RunStep { param([string]$Label, [scriptblock]$ScriptBlock)
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            & $ScriptBlock
            $ex = $LASTEXITCODE
            $sw.Stop()
            return @{ ExitCode = $ex; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2) }
        }
        $r1 = _RunStep -Label "doctor" -ScriptBlock { & $py -m crypto_analyzer.doctor }
        if ($r1.ExitCode -ne 0) {
            _StepFail "doctor" "(exit $($r1.ExitCode), $($r1.Seconds)s)"
            $totalSw.Stop()
            $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
            Write-Host "== VERIFY FAIL (at doctor, exit $($r1.ExitCode), total ${totalSec}s) =="
            exit $r1.ExitCode
        }
        _StepPass "doctor" $r1.Seconds
        $r2 = _RunStep -Label "pytest" -ScriptBlock { & $py -m pytest tests/ }
        if ($r2.ExitCode -ne 0) {
            _StepFail "pytest" "(exit $($r2.ExitCode), $($r2.Seconds)s)"
            $totalSw.Stop()
            $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
            Write-Host "== VERIFY FAIL (at pytest, exit $($r2.ExitCode), total ${totalSec}s) =="
            exit $r2.ExitCode
        }
        _StepPass "pytest" $r2.Seconds
        $ruffOk = $false
        try {
            $r3 = _RunStep -Label "ruff" -ScriptBlock { & $py -m ruff check . --no-cache }
            $ruffOk = ($r3.ExitCode -eq 0)
            if (-not $ruffOk) {
                _StepFail "ruff" "(exit $($r3.ExitCode), $($r3.Seconds)s)"
                $totalSw.Stop()
                $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
                Write-Host "== VERIFY FAIL (at ruff, exit $($r3.ExitCode), total ${totalSec}s) =="
                Write-Host "Fix lint with: .\.venv\Scripts\python.exe -m ruff check . then .\.venv\Scripts\python.exe -m ruff format ."
                exit 1
            }
            _StepPass "ruff" $r3.Seconds
        } catch {
            $totalSw.Stop()
            $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
            _StepFail "ruff" "(not installed or error)"
            Write-Host "== VERIFY FAIL (at ruff, exit 1, total ${totalSec}s) =="
            Write-Host "Install dev deps (includes ruff): .\.venv\Scripts\python.exe -m pip install -e `".[dev]`""
            exit 1
        }
        $r3b = _RunStep -Label "research-only" -ScriptBlock { & $py -c "from crypto_analyzer.spec import validate_research_only_boundary; validate_research_only_boundary()" }
        if ($r3b.ExitCode -ne 0) {
            _StepFail "research-only" "(forbidden keywords in source)"
            $totalSw.Stop()
            $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
            Write-Host "== VERIFY FAIL (at research-only, exit 1, total ${totalSec}s) =="
            Write-Host "Research-only guardrail: no order/submit/broker/api_key/secret/withdraw etc. See spec.py and CONTRIBUTING."
            exit 1
        }
        _StepPass "research-only" $r3b.Seconds
        $diagramDir = Join-Path $root "docs\diagrams"
        $requiredPuml = @("architecture_context", "architecture_internal", "providers_subsystem", "ingestion_sequence", "research_lifecycle")
        $missingPuml = @()
        foreach ($name in $requiredPuml) {
            if (-not (Test-Path (Join-Path $diagramDir "$name.puml"))) { $missingPuml += "$name.puml" }
        }
        if ($missingPuml.Count -gt 0) {
            $totalSw.Stop()
            $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
            _StepFail "diagrams" "(missing source: $($missingPuml -join ', '))"
            Write-Host "== VERIFY FAIL (at diagrams, exit 1, total ${totalSec}s) =="
            exit 1
        }
        try {
            $r4 = _RunStep -Label "diagrams" -ScriptBlock { & (Join-Path $root "scripts\export_diagrams.ps1") -Quiet }
        } catch {
            $totalSw.Stop()
            $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
            _StepFail "diagrams" "(export error: $($_.Exception.Message))"
            Write-Host "== VERIFY FAIL (at diagrams, exit 1, total ${totalSec}s) =="
            Write-Host "Ensure Java and tools from scripts\setup_diagram_tools.ps1 are available."
            exit 1
        }
        if ($r4.ExitCode -ne 0) {
            _StepFail "diagrams" "(export failed, $($r4.Seconds)s)"
            $totalSw.Stop()
            $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
            Write-Host "== VERIFY FAIL (at diagrams, exit $($r4.ExitCode), total ${totalSec}s) =="
            Write-Host "Ensure Java and tools from scripts\setup_diagram_tools.ps1 are available."
            exit 1
        }
        $missingSvg = @()
        foreach ($name in $requiredPuml) {
            if (-not (Test-Path (Join-Path $diagramDir "$name.svg"))) { $missingSvg += "$name.svg" }
        }
        if ($missingSvg.Count -gt 0) {
            $totalSw.Stop()
            $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
            _StepFail "diagrams" "(missing SVG: $($missingSvg -join ', '))"
            Write-Host "== VERIFY FAIL (at diagrams, exit 1, total ${totalSec}s) =="
            exit 1
        }
        _StepPass "diagrams" $r4.Seconds
        $totalSw.Stop()
        $totalSec = [math]::Round($totalSw.Elapsed.TotalSeconds, 2)
        Write-Host "== VERIFY PASS (total ${totalSec}s) =="
        exit 0
    }
    default          {
        if ($Command) { & $py $Command @filtered; exit $LASTEXITCODE } else {
            Write-Host "Usage: .\scripts\run.ps1 [-SkipDoctor] <command> [args...]"
            Write-Host "Commands: poll, universe-poll, materialize, analyze, scan, report, reportv2,"
            Write-Host "          daily, backtest, walkforward, streamlit, api, doctor, test,"
            Write-Host "          demo, check-dataset, verify"
            Write-Host "  -SkipDoctor  Skip pre-flight doctor (default: run doctor before most commands)"
            exit 1
        }
    }
}
