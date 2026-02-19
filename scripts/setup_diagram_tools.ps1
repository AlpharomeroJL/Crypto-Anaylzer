# In-repo, no-admin setup: PlantUML jar + portable Graphviz.
# Run once from repo root (or from scripts/); requires Java and PowerShell.
# Usage: .\scripts\setup_diagram_tools.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$plantumlDir = Join-Path $root "tools/plantuml"
$plantumlJar = Join-Path $plantumlDir "plantuml.jar"
$graphvizDir = Join-Path $root "tools/graphviz"
$graphvizBin = Join-Path $graphvizDir "bin"

# Fixed URLs for deterministic setup
$plantumlUrl = "https://github.com/plantuml/plantuml/releases/download/v1.2026.1/plantuml-1.2026.1.jar"
$graphvizZipUrl = "https://gitlab.com/api/v4/projects/4207231/packages/generic/graphviz-releases/14.1.2/windows_10_cmake_Release_Graphviz-14.1.2-win64.zip"

# --- PlantUML ---
New-Item -ItemType Directory -Force -Path $plantumlDir | Out-Null
if (Test-Path $plantumlJar) {
    Write-Host "PlantUML jar already present: $plantumlJar"
} else {
    Write-Host "Downloading PlantUML jar..."
    Invoke-WebRequest -Uri $plantumlUrl -OutFile $plantumlJar -UseBasicParsing
    Write-Host "Saved: $plantumlJar"
}

# --- Graphviz (portable zip) ---
$dotExe = Join-Path $graphvizBin "dot.exe"
if (Test-Path $dotExe) {
    Write-Host "Graphviz dot.exe already present: $dotExe"
} else {
    $zipPath = Join-Path $env:TEMP "graphviz-portable.zip"
    $extractPath = Join-Path $env:TEMP "graphviz_extract_$([Guid]::NewGuid().ToString('N').Substring(0,8))"

    try {
        Write-Host "Downloading Graphviz portable zip..."
        Invoke-WebRequest -Uri $graphvizZipUrl -OutFile $zipPath -UseBasicParsing

        New-Item -ItemType Directory -Force -Path $extractPath | Out-Null
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

        # Zip may have one top-level folder (e.g. Release or Graphviz-14.1.2) with bin/dot.exe
        $innerDirs = Get-ChildItem $extractPath -Directory
        $sourceRoot = $null
        if ($innerDirs.Count -eq 1 -and (Test-Path (Join-Path $innerDirs[0].FullName "bin\dot.exe"))) {
            $sourceRoot = $innerDirs[0].FullName
        } elseif (Test-Path (Join-Path $extractPath "bin\dot.exe")) {
            $sourceRoot = $extractPath
        }
        if (-not $sourceRoot) {
            throw "Could not find bin\dot.exe in extracted Graphviz zip. Check structure under: $extractPath"
        }

        New-Item -ItemType Directory -Force -Path $graphvizDir | Out-Null
        Copy-Item -Path (Join-Path $sourceRoot "*") -Destination $graphvizDir -Recurse -Force
        Write-Host "Graphviz installed: $graphvizBin"
    } finally {
        if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
        if (Test-Path $extractPath) { Remove-Item $extractPath -Recurse -Force }
    }
}

if (!(Test-Path $dotExe)) {
    throw "Expected dot.exe at $dotExe after setup."
}
Write-Host "Setup complete. Run: .\scripts\export_diagrams.ps1"
