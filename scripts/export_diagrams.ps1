# Export PlantUML .puml -> SVG and PNG. Requires: Java (on PATH or in Program Files), tools from setup_diagram_tools.ps1.
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

Write-Host "Exporting PlantUML diagrams from $diagramPath"
Get-ChildItem $diagramPath -Filter *.puml -Recurse | ForEach-Object {
  Write-Host " - $($_.FullName)"
  & $javaExe -jar $plantumlJar -tsvg $_.FullName
  & $javaExe -jar $plantumlJar -tpng $_.FullName
}
Write-Host "Done."
