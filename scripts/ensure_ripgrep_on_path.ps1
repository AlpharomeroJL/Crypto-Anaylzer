# Add WinGet-installed ripgrep (rg.exe) to the *user* PATH if missing.
# GrapeRoot's graperoot.ps1 uses Get-Command rg; portable installs often omit PATH.
# Safe to run multiple times (idempotent).
# Usage: .\scripts\ensure_ripgrep_on_path.ps1

$ErrorActionPreference = "Stop"

$found = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" `
    -Filter "rg.exe" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "BurntSushi|ripgrep" } |
    Select-Object -First 1

if (-not $found) {
    Write-Host "rg.exe not found under WinGet Packages. Install with:"
    Write-Host "  winget install --id BurntSushi.ripgrep.MSVC -e --accept-source-agreements"
    exit 1
}

$binDir = $found.Directory.FullName
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$paths = @()
if ($userPath) {
    $paths = $userPath -split ";" | Where-Object { $_ -and $_.Trim() }
}
$already = $paths | Where-Object { $_ -ieq $binDir }
if ($already) {
    Write-Host "Ripgrep already on user PATH: $binDir"
    exit 0
}

$newPath = ($paths + $binDir) -join ";"
[Environment]::SetEnvironmentVariable("Path", $newPath, "User")
Write-Host "Added to user PATH: $binDir"
Write-Host "Open a new terminal (or restart Cursor) and run: rg --version"
