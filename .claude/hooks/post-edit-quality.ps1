$ErrorActionPreference = "Continue"

if ($env:CLAUDE_PROJECT_DIR) {
    $ProjectRoot = $env:CLAUDE_PROJECT_DIR
} else {
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

Set-Location $ProjectRoot

$VenvRuff = Join-Path $ProjectRoot ".venv\Scripts\ruff.exe"

if (Test-Path $VenvRuff) {
    & $VenvRuff check src/modular_rag tests --select E,F,I --quiet
    exit $LASTEXITCODE
}

$RuffCommand = Get-Command ruff -ErrorAction SilentlyContinue
if ($RuffCommand) {
    ruff check src/modular_rag tests --select E,F,I --quiet
    exit $LASTEXITCODE
}

Write-Host "ruff not found; install dev dependencies with: pip install -e `".[v1,dev]`""
exit 0
