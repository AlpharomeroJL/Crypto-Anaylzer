# Crypto-Analyzer: run commands using .venv (avoids ModuleNotFoundError).
# Delegates via: python -m crypto_analyzer <command> (does not rely on PATH for crypto-analyzer).
# Doctor-first: runs doctor before most commands unless -SkipDoctor is passed.
# Must run from repo root; script will cd to repo root (parent of scripts/).
# Usage: .\scripts\run.ps1 [-SkipDoctor] <command> [args...]
# Commands: poll, universe-poll, materialize, report, reportv2, case_study_liqshock, streamlit, doctor, test, demo, check-dataset
param(
    [switch]$SkipDoctor,
    [Parameter(Position = 0)]$Command,
    [Parameter(ValueFromRemainingArguments = $true)]$Passthrough
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if ($env:VIRTUAL_ENV) {
    $py = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
} else {
    $py = Join-Path $root ".venv\Scripts\python.exe"
}
if (-not (Test-Path $py)) {
    Write-Error "Python venv not found at $py. Create .venv at repo root or set VIRTUAL_ENV. See README Quickstart."
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
    & $py -m crypto_analyzer doctor
    $doctorExit = $LASTEXITCODE
    if ($doctorExit -ne 0) {
        exit $doctorExit
    }
}

switch ($Command) {
    "poll"           { & $py -m crypto_analyzer poll --interval 60 @filtered; exit $LASTEXITCODE }
    "universe-poll"  { & $py -m crypto_analyzer universe-poll @filtered; exit $LASTEXITCODE }
    "materialize"    { & $py -m crypto_analyzer materialize @filtered; exit $LASTEXITCODE }
    "analyze"        { & $py -m crypto_analyzer analyze @filtered; exit $LASTEXITCODE }
    "scan"           { & $py -m crypto_analyzer scan @filtered; exit $LASTEXITCODE }
    "report"         { & $py -m crypto_analyzer report @filtered; exit $LASTEXITCODE }
    "reportv2"       { & $py -m crypto_analyzer reportv2 @filtered; exit $LASTEXITCODE }
    "case_study_liqshock" {
        $baseArgs = @(
            "--signals", "liquidity_shock_reversion",
            "--portfolio", "advanced",
            "--execution-evidence",
            "--reality-check",
            "--case-study", "liqshock"
        )
        $filteredForReport = @($filtered | Where-Object { $_ -ne "--snapshot" })
        & $py -m crypto_analyzer reportv2 @baseArgs @filteredForReport
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) { exit $exitCode }
        $outDir = "reports"
        $freq = "1h"
        $rcNsim = 200; $rcMethod = "stationary"; $rcBlock = 12; $rcSeed = 42
        $doSnapshot = $false
        for ($i = 0; $i -lt $filtered.Count; $i++) {
            if ($filtered[$i] -eq "--out-dir" -and ($i + 1) -lt $filtered.Count) { $outDir = $filtered[$i + 1] }
            if ($filtered[$i] -eq "--freq" -and ($i + 1) -lt $filtered.Count) { $freq = $filtered[$i + 1] }
            if ($filtered[$i] -eq "--rc-n-sim" -and ($i + 1) -lt $filtered.Count) { $rcNsim = $filtered[$i + 1] }
            if ($filtered[$i] -eq "--rc-method" -and ($i + 1) -lt $filtered.Count) { $rcMethod = $filtered[$i + 1] }
            if ($filtered[$i] -eq "--rc-avg-block-length" -and ($i + 1) -lt $filtered.Count) { $rcBlock = $filtered[$i + 1] }
            if ($filtered[$i] -eq "--rc-seed" -and ($i + 1) -lt $filtered.Count) { $rcSeed = $filtered[$i + 1] }
            if ($filtered[$i] -eq "--snapshot") { $doSnapshot = $true }
        }
        $outPath = Join-Path $root $outDir
        $latest = Get-ChildItem -Path $outPath -Filter "research_v2_*.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $latest) {
            Write-Host "case_study_liqshock: No research_v2_*.md found in $outPath"
            exit 0
        }
        $reportTime = $latest.LastWriteTime
        $destName = "case_study_liqshock_$freq.md"
        $destPath = Join-Path $outPath $destName
        Copy-Item -Path $latest.FullName -Destination $destPath -Force
        Write-Host "case_study_liqshock: source $($latest.FullName)"
        Write-Host "case_study_liqshock: destination $destPath"
        $csvDir = Join-Path $outPath "csv"
        $runId = $null
        $capSameRun = @()
        if (Test-Path $csvDir) {
            $capSameRun = Get-ChildItem -Path $csvDir -Filter "capacity_curve_liqshock_*.csv" -ErrorAction SilentlyContinue | Where-Object { [math]::Abs(($_.LastWriteTime - $reportTime).TotalSeconds) -le 15 }
            if ($capSameRun.Count -eq 0) { $capSameRun = Get-ChildItem -Path $csvDir -Filter "capacity_curve_liqshock_*.csv" -ErrorAction SilentlyContinue | Where-Object { [math]::Abs(($_.LastWriteTime - $reportTime).TotalSeconds) -le 60 } }
            if ($capSameRun.Count -gt 0) { $capSameRun = $capSameRun | Sort-Object LastWriteTime -Descending }
            if ($capSameRun.Count -gt 0) {
                $firstCap = @($capSameRun)[0]
                $runId = ($firstCap.BaseName -split '_')[-1]
            }
        }
        $rcSummary = $null
        if (Test-Path $csvDir) {
            $rcCandidates = Get-ChildItem -Path $csvDir -Filter "reality_check_summary_*.json" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $reportTime.AddSeconds(-5) -and $_.LastWriteTime -le $reportTime.AddSeconds(15) }
            if ($rcCandidates.Count -gt 0) { $rcSummary = $rcCandidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1 }
        }
        $bestVariant = $null
        $memoContent = Get-Content -Path $destPath -Raw -ErrorAction SilentlyContinue
        if ($memoContent) {
            foreach ($line in ($memoContent -split "`n")) {
                if ($line -match '^\|\s*(liqshock_[^|]+)\|' -and $line -match '\|\s*Survived\s*\|') { $bestVariant = $Matches[1].Trim(); break }
            }
            if (-not $bestVariant) {
                foreach ($line in ($memoContent -split "`n")) {
                    if ($line -match '^\|\s*(liqshock_[^|]+)\|') { $bestVariant = $Matches[1].Trim(); break }
                }
            }
        }
        if (-not $runId) { $runId = "unknown" }
        $latestDir = Join-Path $outPath "case_study_liqshock_latest"
        New-Item -ItemType Directory -Path $latestDir -Force | Out-Null
        Get-ChildItem -Path $latestDir -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Copy-Item -Path $destPath -Destination (Join-Path $latestDir $destName) -Force
        if ($rcSummary) { Copy-Item -Path $rcSummary.FullName -Destination $latestDir -Force }
        if ($runId -ne "unknown" -and $bestVariant) {
            $capFile = Join-Path $csvDir "capacity_curve_${bestVariant}_${runId}.csv"
            $execFile = Join-Path $csvDir "execution_evidence_${bestVariant}_${runId}.json"
            if (Test-Path $capFile) { Copy-Item -Path $capFile -Destination $latestDir -Force }
            if (Test-Path $execFile) { Copy-Item -Path $execFile -Destination $latestDir -Force }
        }
        if ($runId -ne "unknown" -and -not $bestVariant -and (Test-Path $csvDir)) {
            $oneCap = Get-ChildItem -Path $csvDir -Filter "capacity_curve_liqshock_*_${runId}.csv" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($oneCap) {
                Copy-Item -Path $oneCap.FullName -Destination $latestDir -Force
                $base = $oneCap.BaseName -replace '^capacity_curve_', ''
                $v = $base -replace "_${runId}$", ''
                $execFile = Join-Path $csvDir "execution_evidence_${v}_${runId}.json"
                if (Test-Path $execFile) { Copy-Item -Path $execFile -Destination $latestDir -Force }
            }
        }
        $barsMatchPct = $null
        if ($memoContent -match 'bars columns matched:\s*\d+\s*\(([\d.]+)%\)') { $barsMatchPct = [double]$Matches[1] }
        $gitCommit = (& git rev-parse --short HEAD 2>$null)
        if (-not $gitCommit) { $gitCommit = "" }
        $metaObj = @{
            run_id = $runId
            freq = $freq
            rc_n_sim = [int]$rcNsim
            rc_method = $rcMethod
            rc_avg_block_length = [int]$rcBlock
            rc_seed = [int]$rcSeed
            timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
            git_commit = $gitCommit
            report_source = $latest.FullName
            report_dest = $destPath
            out_dir = $outPath
        }
        if ($null -ne $barsMatchPct) { $metaObj["bars_match_pct"] = $barsMatchPct }
        $meta = $metaObj | ConvertTo-Json -Depth 3
        $metaPath = Join-Path $latestDir "run_metadata.json"
        $meta | Set-Content -Path $metaPath -Encoding UTF8
        $readmePath = Join-Path $latestDir "README.txt"
        "Open the memo first: $destName" | Set-Content -Path $readmePath -Encoding UTF8
        Write-Host "case_study_liqshock: deliverable folder $latestDir (memo + RC summary + best variant capacity/exec + run_metadata.json)"
        if ($doSnapshot -and $runId -ne "unknown") {
            $snapshotBase = Join-Path $outPath "case_study_liqshock_runs"
            $snapshotDir = Join-Path $snapshotBase $runId
            if (Test-Path $snapshotDir) { $snapshotDir = Join-Path $snapshotBase "${runId}_$(Get-Date -Format 'yyyyMMdd_HHmmss')" }
            New-Item -ItemType Directory -Path $snapshotDir -Force | Out-Null
            Get-ChildItem -Path $latestDir -File -ErrorAction SilentlyContinue | ForEach-Object { Copy-Item -Path $_.FullName -Destination $snapshotDir -Force }
            Write-Host "case_study_liqshock: snapshot (frozen) $snapshotDir"
        }
        exit 0
    }
    "daily"          { & $py -m crypto_analyzer daily @filtered; exit $LASTEXITCODE }
    "backtest"       { & $py -m crypto_analyzer backtest @filtered; exit $LASTEXITCODE }
    "walkforward"    { & $py -m crypto_analyzer walkforward @filtered; exit $LASTEXITCODE }
    "streamlit"      { & $py -m crypto_analyzer streamlit @filtered; exit $LASTEXITCODE }
    "api"            { & $py -m crypto_analyzer api @filtered; exit $LASTEXITCODE }
    "doctor"         { & $py -m crypto_analyzer doctor @filtered; exit $LASTEXITCODE }
    "test"           { & $py -m pytest tests/ @filtered; exit $LASTEXITCODE }
    "demo"           { & $py -m crypto_analyzer demo @filtered; exit $LASTEXITCODE }
    "check-dataset"  { & $py -m crypto_analyzer check-dataset @filtered; exit $LASTEXITCODE }
    "null_suite"     { & $py -m crypto_analyzer null_suite @filtered; exit $LASTEXITCODE }
    "promotion"      { & $py -m crypto_analyzer promotion @filtered; exit $LASTEXITCODE }
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
        $r1 = _RunStep -Label "doctor" -ScriptBlock { & $py -m crypto_analyzer doctor }
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
            Write-Host "          case_study_liqshock, daily, backtest, walkforward, streamlit, api, doctor, test,"
            Write-Host "          demo, check-dataset, verify"
            Write-Host "  -SkipDoctor  Skip pre-flight doctor (default: run doctor before most commands)"
            exit 1
        }
    }
}
