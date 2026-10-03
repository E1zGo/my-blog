$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    Write-Host 'Create the environment first: py -3 -m venv .venv'
    Write-Host 'Then install: .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt'
    exit 1
}
Write-Host 'Checking ResearchPilot environment and data...'
& $projectPython -m researchpilot.maintenance doctor
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'ResearchPilot: http://127.0.0.1:8765'
& $projectPython -m uvicorn researchpilot.app:app --host 127.0.0.1 --port 8765
