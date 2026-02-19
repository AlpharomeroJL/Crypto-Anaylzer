# Export PlantUML .puml -> SVG and PNG. Requires: Java (on PATH or in Program Files), tools from setup_diagram_tools.ps1.
# Embeds git commit hash in each SVG <title> for traceability.
# -Quiet: suppress per-file and "Exporting..." output (e.g. when called from verify).
param([switch]$Quiet)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$diagramPath = Join-Path $root "docs/diagrams"
$plantumlJar = Join-Path $root "tools/plantuml/plantuml.jar"
$graphvizBin = Join-Path $root "tools/graphviz/bin"

if (!(Test-Path $plantumlJar)) { throw "Missing $plantumlJar (download plantuml.jar)" }
if (!(Test-Path (Join-Path $graphvizBin "dot.exe"))) { throw "Missing dot.exe in $graphvizBin (portable Graphviz)" }

# Prefer java on PATH; else look in common Windows install locations
$javaExe = $null
if (Get-Command java -ErrorAction SilentlyContinue) { $javaExe = "java" }
if (-not $javaExe) {
  $searchPaths = @(
    (Join-Path $env:ProgramFiles "Java\*\bin\java.exe"),
    (Join-Path $env:ProgramFiles "Eclipse Adoptium\jdk-*\bin\java.exe"),
    (Join-Path $env:ProgramFiles "Microsoft\jdk-*\bin\java.exe")
  )
  foreach ($pat in $searchPaths) {
    $found = Get-Item $pat -ErrorAction SilentlyContinue | Sort-Object { $_.FullName } -Descending | Select-Object -First 1
    if ($found) { $javaExe = $found.FullName; break }
  }
}
if (-not $javaExe) { throw "Java not found. Install a JRE/JDK (e.g. https://adoptium.net/) and ensure java is on PATH or in Program Files." }

$env:GRAPHVIZ_DOT = (Join-Path $graphvizBin "dot.exe")

# Git commit hash for diagram stamping (traceable to code revision)
$gitHash = $null
try {
  $gitHash = (git -C $root rev-parse --short HEAD 2>$null)
} catch {}
if (-not $gitHash) { $gitHash = "unknown" }

if (-not $Quiet) { Write-Host "Diagrams:"; Write-Host "Exporting PlantUML from $diagramPath (stamp: $gitHash)" }
Get-ChildItem $diagramPath -Filter *.puml -Recurse | ForEach-Object {
  if (-not $Quiet) { Write-Host " - $($_.Name)" }
  & $javaExe -jar $plantumlJar -tsvg $_.FullName
  & $javaExe -jar $plantumlJar -tpng $_.FullName
  $baseName = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
  $svgPath = Join-Path $diagramPath "$baseName.svg"
  if (Test-Path $svgPath) {
    $content = Get-Content -Path $svgPath -Raw -Encoding UTF8
    # Append git hash to existing <title> for traceability to code revision
    $content = $content -replace "(<title>[^<]*)(</title>)", "`$1 ($gitHash)`$2"
    Set-Content -Path $svgPath -Value $content -NoNewline -Encoding UTF8
  }
}
if (-not $Quiet) { Write-Host "Done." }
