param(
    [string]$FreeCadPython = "C:\Users\pz9079\AppData\Local\Programs\FreeCAD 1.1\bin\python.exe"
)

$ErrorActionPreference = "Stop"

python -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "Unit tests failed"
}

python -m compileall -q fc_deburr deburr_app.py
if ($LASTEXITCODE -ne 0) {
    throw "Host Python compile check failed"
}

if (-not (Test-Path -LiteralPath $FreeCadPython)) {
    throw "FreeCAD Python was not found: $FreeCadPython"
}

& $FreeCadPython -m compileall -q fc_deburr deburr_app.py
if ($LASTEXITCODE -ne 0) {
    throw "FreeCAD Python compile check failed"
}

& $FreeCadPython .\tests\freecad_integration_check.py
if ($LASTEXITCODE -ne 0) {
    throw "FreeCAD integration check failed"
}

Write-Host "All deburr-engine verification checks passed."
