Param(
  [string]$HostAddr = "127.0.0.1",
  [int]$Port = 8000,
  [int]$MaxPortTries = 20,
  [string]$Freq = "1h",
  [string]$OutDir = "reports"
)

# If you see WinError 10048 (address already in use), kill the existing server:
#   netstat -ano | findstr :<Port>   # find the PID
#   taskkill /F /PID <pid>           # kill it
# Or simply pass a different port: .\tools\triage_api.ps1 -Port 8001

$ErrorActionPreference = "Stop"

function Test-PortFree {
  param([string]$HostAddr, [int]$Port)
  try {
    $conn = Test-NetConnection -ComputerName $HostAddr -Port $Port -WarningAction SilentlyContinue
    return (-not $conn.TcpTestSucceeded)
  } catch {
    # If Test-NetConnection isn't available, fall back to netstat parsing
    $listening = netstat -ano | Select-String -Pattern "LISTENING" | Select-String -Pattern ":$Port\s"
    return ($null -eq $listening)
  }
}

function Find-FreePort {
  param([string]$HostAddr, [int]$StartPort, [int]$MaxTries)
  for ($i=0; $i -le $MaxTries; $i++) {
    $p = $StartPort + $i
    if (Test-PortFree -HostAddr $HostAddr -Port $p) {
      return $p
    }
  }
  throw "No free port found in range $StartPort..$($StartPort + $MaxTries)"
}

Write-Host "== Step 0: Repo preflight =="
if (-not (Test-Path ".\scripts\run.ps1")) { throw "scripts/run.ps1 not found. Run from repo root." }

Write-Host "== Step 1: Doctor =="
.\scripts\run.ps1 doctor

Write-Host "== Step 2: Choose a free port =="
$freePort = Find-FreePort -HostAddr $HostAddr -StartPort $Port -MaxTries $MaxPortTries
if ($freePort -ne $Port) {
  Write-Host "Port $Port is busy. Using $freePort."
} else {
  Write-Host "Port $Port is free."
}

Write-Host "== Step 3: Start API in background (new window) =="
# Start in a new PowerShell window so it stays alive
$apiCmd = ".\scripts\run.ps1 api --host $HostAddr --port $freePort"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd | Out-Null
Start-Sleep -Seconds 2

Write-Host "== Step 4: Verify /health =="
curl.exe "http://$HostAddr`:$freePort/health"
Write-Host ""

Write-Host "== Step 5: Generate an experiment run (reportv2) =="
.\scripts\run.ps1 reportv2 --freq $Freq --out-dir $OutDir

Write-Host "== Step 6: Verify /experiments/recent =="
curl.exe "http://$HostAddr`:$freePort/experiments/recent"
Write-Host ""

Write-Host "== Step 7: If still empty, show likely experiment DB files =="
Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match "experiments\.db$" -or $_.Name -match "experiment" } |
  Select-Object FullName, Length, LastWriteTime |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 15

Write-Host ""
Write-Host "Done."
Write-Host "API should be running at: http://$HostAddr`:$freePort"
Write-Host "Tip: If /experiments/recent is still [], the API and reportv2 may be pointing at different EXPERIMENT_DB_PATH values."
Write-Host "Tip: If you see WinError 10048, a server is already running on that port. Use netstat/taskkill or change -Port."
