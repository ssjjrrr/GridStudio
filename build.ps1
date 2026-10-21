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
    & $buildPython scripts\build.py
    if ($LASTEXITCODE -ne 0) { throw "Build failed" }
}
finally { Pop-Location }
