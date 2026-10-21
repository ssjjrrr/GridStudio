param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Failed to create Python environment" }
    }
    $buildPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    & $buildPython -m pip install -r requirements.txt pyinstaller==6.20.0
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
    & $buildPython -m PyInstaller --noconfirm --clean --distpath dist --workpath build\temp GridStudio.spec
    if ($LASTEXITCODE -ne 0) { throw "Build failed" }
    Copy-Item -LiteralPath README.txt,CHANGELOG.md,LICENSE,THIRD_PARTY_NOTICES.txt -Destination dist\GridStudio -Force
    Copy-Item -LiteralPath licenses -Destination dist\GridStudio -Recurse -Force
    if (Test-Path -LiteralPath demo) { Copy-Item -LiteralPath demo -Destination dist\GridStudio -Recurse -Force }
    Copy-Item -LiteralPath benchmarks\README.txt -Destination dist\GridStudio\INTERACTION_PERFORMANCE.txt -Force
    Copy-Item -LiteralPath benchmarks\performance.json -Destination dist\GridStudio\PERFORMANCE.json -Force
    if (Test-Path -LiteralPath docs\validation-1.0.0.md) {
        Copy-Item -LiteralPath docs\validation-1.0.0.md -Destination dist\GridStudio\VALIDATION.md -Force
    }
    Write-Output "Built: $projectRoot\dist\GridStudio\GridStudio.exe"
}
finally { Pop-Location }
