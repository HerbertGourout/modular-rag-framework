param(
    [ValidateSet("quick", "full", "integration", "e2e", "all", "help")]
    [string]$Mode = "help"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Python = if (Test-Path ".venv\Scripts\python.exe") {
    ".venv\Scripts\python.exe"
} else {
    "python"
}
$RunTemp = Join-Path $ProjectRoot "tmp/check-$PID"
New-Item -ItemType Directory -Force $RunTemp | Out-Null
$env:TMP = $RunTemp
$env:TEMP = $RunTemp

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
    Write-Host "`n== $Label ==" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
}

function Invoke-Quick {
    Invoke-Checked "Ruff syntax and imports" {
        & $Python -m ruff check . --select E,F,I
    }
}

function Invoke-Full {
    Invoke-Checked "Ruff" {
        & $Python -m ruff check . --select E,F,I,N,W,UP,B,C4
    }
    Invoke-Checked "Compilation" {
        & $Python -m compileall -q src/modular_rag scripts examples docker
    }
    Invoke-Checked "Strict layering" { & $Python scripts/check_layering.py --strict }
    Invoke-Checked "Documentation" { & $Python scripts/check_docs.py }
    Invoke-Checked "Whitespace" { git diff --check }

    Write-Host "`n== MyPy baseline ==" -ForegroundColor Cyan
    $baseline = Get-Content .claude/mypy-baseline.txt |
        Where-Object { $_ -and -not $_.StartsWith("#") } |
        Select-Object -First 1
    $mypyOutput = & $Python -m mypy src/modular_rag --no-error-summary 2>&1
    $errors = @($mypyOutput | Select-String "error:").Count
    if ($errors -gt [int]$baseline) {
        $mypyOutput | Write-Host
        throw "MyPy has $errors errors; baseline is $baseline"
    }
    Write-Host "MyPy: $errors errors (baseline: $baseline)"

    Write-Host "`n== Runnable manifests ==" -ForegroundColor Cyan
    $env:QDRANT_URL = "http://localhost:6333"
    $env:QDRANT_API_KEY = "smoke-test-key"
    $env:AUDIT_DATABASE_URL = "postgresql://smoke-test/db"
    @'
from pathlib import Path
from modular_rag.app.bootstrap import load_application

paths = sorted(Path("manifests/presets").glob("*.yaml")) + [Path("docker/local-hybrid-rag.yaml")]
for path in paths:
    application = load_application(path)
    print(f"{path.name} wires cleanly (engine={application.engine_name})")
    application.close()
'@ | & $Python -
    if ($LASTEXITCODE -ne 0) { throw "Runnable manifest validation failed" }

    Invoke-Checked "Unit tests" {
        & $Python -m pytest tests/unit -q -p no:cacheprovider --basetemp "$RunTemp/unit"
    }
    Invoke-Checked "Contract tests" {
        & $Python -m pytest tests/contract -q -p no:cacheprovider --basetemp "$RunTemp/contract"
    }
}

function Test-Port([string]$HostName = "127.0.0.1", [int]$Port) {
    (Test-NetConnection -ComputerName $HostName -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
}

function Invoke-Integration {
    if (-not (Test-Port -Port 6333)) {
        Write-Warning "Qdrant is not available on localhost:6333; integration tests skipped."
        return
    }
    Invoke-Checked "Integration tests" {
        & $Python -m pytest tests/integration -q -m integration -p no:cacheprovider --basetemp "$RunTemp/integration"
    }
}

# tests/e2e/ holds two scenarios with different prerequisites:
#   - test_simple_qa_pipeline.py needs Qdrant + an LLM API key.
#   - test_secure_preset_e2e.py needs Qdrant + PostgreSQL, and deliberately needs NO LLM key
#     (deterministic embedder/generator — see that file's own module docstring).
# All three prerequisites are required up front and this throws if any is missing, rather than
# letting `pytest -m e2e` run with one scenario's tests silently skipped — a skip-heavy "all
# skipped" run still exits 0, which would let this gate report success without actually
# exercising the secure/governance scenario (Codex review, HIGH-001).
function Invoke-E2E {
    # Resolve the same overrides tests/e2e/test_secure_preset_e2e.py itself honors
    # (MRAG_TEST_QDRANT_URL / MRAG_TEST_POSTGRES_DSN) instead of hardcoding localhost —
    # a container/CI network commonly points these elsewhere, and probing the wrong host
    # made this gate fail even when the actual test target was reachable (Codex review,
    # MED-001).
    # [Uri].Port alone is wrong for a portless URL/DSN: it silently returns the *scheme's*
    # default (80 for http://, -1 for a scheme .NET doesn't recognize like postgresql://) —
    # neither is 6333/5432. .IsDefaultPort is true exactly when no explicit port was in the
    # original string, which is when we need our own service default instead of trusting
    # .Port (Codex review, MED-001 — matches tests/e2e/test_secure_preset_e2e.py's own
    # `parsed.port or default_port` fallback exactly).
    $qdrantUrlRaw = if ($env:MRAG_TEST_QDRANT_URL) { $env:MRAG_TEST_QDRANT_URL } else { "http://localhost:6333" }
    $qdrantUri = [Uri]$qdrantUrlRaw
    $qdrantPort = if ($qdrantUri.IsDefaultPort) { 6333 } else { $qdrantUri.Port }
    $postgresDsnRaw = if ($env:MRAG_TEST_POSTGRES_DSN) { $env:MRAG_TEST_POSTGRES_DSN } else { "postgresql://postgres:postgres@localhost:5432/postgres" }
    $postgresUri = [Uri]$postgresDsnRaw
    $postgresPort = if ($postgresUri.IsDefaultPort) { 5432 } else { $postgresUri.Port }

    if (-not (Test-Port -HostName $qdrantUri.Host -Port $qdrantPort)) {
        throw "Qdrant is not reachable at $($qdrantUri.Host):$qdrantPort (from MRAG_TEST_QDRANT_URL, default localhost:6333)"
    }
    if (-not (Test-Port -HostName $postgresUri.Host -Port $postgresPort)) {
        throw "PostgreSQL is not reachable at $($postgresUri.Host):$postgresPort (from MRAG_TEST_POSTGRES_DSN, default localhost:5432; required by tests/e2e/test_secure_preset_e2e.py)"
    }
    if (-not $env:OPENAI_API_KEY -and -not $env:ANTHROPIC_API_KEY) {
        throw "Set OPENAI_API_KEY or ANTHROPIC_API_KEY before running E2E tests (required by tests/e2e/test_simple_qa_pipeline.py; test_secure_preset_e2e.py itself needs none)"
    }
    Invoke-Checked "E2E tests" {
        & $Python -m pytest tests/e2e -q -m e2e -p no:cacheprovider --basetemp "$RunTemp/e2e"
    }
}

switch ($Mode) {
    "quick" { Invoke-Quick }
    "full" { Invoke-Full }
    "integration" { Invoke-Integration }
    "e2e" { Invoke-E2E }
    "all" { Invoke-Full; Invoke-Integration; Invoke-E2E }
    default {
        Write-Host "Usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1 quick|full|integration|e2e|all"
        Write-Host "Linux/macOS equivalent: ./scripts/check.sh <mode>"
    }
}
