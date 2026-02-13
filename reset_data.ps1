# Reset data: stop CryptoPoller, archive DB + plots to timestamped folder, restart service.
# Run PowerShell as Administrator so NSSM can stop/start the service.
# Dashboard/analyzer use DB in repo root; they will not load from archive/ unless you change the path.

param(
    [switch]$NoRestart  # If set, do not restart CryptoPoller after archiving
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$nssm = "C:\nssm\win64\nssm.exe"
if (-not (Test-Path $nssm)) { $nssm = "C:\nssm\nssm.exe" }
if (-not (Test-Path $nssm)) {
    Write-Error "NSSM not found. Install to C:\nssm\win64\ or C:\nssm\"
    exit 1
}

$archiveDir = Join-Path $repoRoot "archive"
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$destDir = Join-Path $archiveDir $stamp

Write-Host "Stopping CryptoPoller..."
& $nssm stop CryptoPoller
Start-Sleep -Seconds 2

if (-not (Test-Path $archiveDir)) { New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null }
New-Item -ItemType Directory -Path $destDir -Force | Out-Null

$dbPath = Join-Path $repoRoot "dex_data.sqlite"
$plotsPath = Join-Path $repoRoot "plots"

if (Test-Path $dbPath) {
    Copy-Item -Path $dbPath -Destination (Join-Path $destDir "dex_data.sqlite") -Force
    Remove-Item -Path $dbPath -Force
    Write-Host "Archived and removed: dex_data.sqlite"
} else {
    Write-Host "No dex_data.sqlite found; skipping."
}

if (Test-Path $plotsPath) {
    Copy-Item -Path $plotsPath -Destination (Join-Path $destDir "plots") -Recurse -Force
    Remove-Item -Path $plotsPath -Recurse -Force
    Write-Host "Archived and removed: plots/"
} else {
    Write-Host "No plots/ folder found; skipping."
}

Write-Host "Archive written to: $destDir"

if (-not $NoRestart) {
    Write-Host "Starting CryptoPoller..."
    & $nssm start CryptoPoller
    Write-Host "Done. New data will be written to repo root. Dashboard uses same DB path."
} else {
    Write-Host "Skipping service start ( -NoRestart ). Run: & `"$nssm`" start CryptoPoller"
}
