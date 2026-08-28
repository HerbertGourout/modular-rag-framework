$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

if (-not (Test-Path ".githooks/pre-push")) {
    throw "Missing versioned hook: .githooks/pre-push"
}

git config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    throw "Unable to configure core.hooksPath"
}

Write-Host "Git hooks installed for this clone (core.hooksPath=.githooks)." -ForegroundColor Green
Write-Host "Every git push now runs scripts/check_docs.py and stops on documentation drift."
