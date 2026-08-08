#!/bin/bash
# Unified validation script for modular-rag-framework
# Supports quick (micro-edits) and full (comprehensive) validation modes
# Usage: ./scripts/check.sh [quick|full|all|help]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}▶ $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# ============================================================================
# QUICK CHECK — Fast validation for micro-edits (< 1min)
# Use: daily, pre-commit, or after small changes
# ============================================================================
check_quick() {
    print_header "QUICK CHECK — Syntax & Import Order (~30s)"
    
    echo "Linting Python syntax, undefined names, import order..."
    if ruff check src/modular_rag/ tests/ --select E,F,I --fix-only --output-format=concise; then
        print_success "Ruff syntax check passed"
    else
        print_error "Ruff syntax check failed"
        return 1
    fi
    
    print_success "Quick check completed"
    echo ""
}

# ============================================================================
# FULL CHECK — Comprehensive validation (~ 2-5 min)
# Use: pre-merge, CI/CD, or before releasing
# ============================================================================
check_full() {
    print_header "FULL CHECK — Compilation + Layering + Types + Manifest + Unit + Contract (~2-5 min)"

    # Step 1: Ruff linting (syntax, imports, naming)
    echo "Step 1/7: Linting code quality..."
    if ruff check src/modular_rag/ tests/ --select E,F,I,N,W,UP,B,C4 --output-format=concise; then
        print_success "Ruff linting passed"
    else
        print_error "Ruff linting failed"
        return 1
    fi

    # Step 2: Compilation check
    echo ""
    echo "Step 2/7: Compilation check..."
    if python -m compileall -q src/modular_rag; then
        print_success "Compilation check passed"
    else
        print_error "Compilation check failed"
        return 1
    fi

    # Step 3: Strict layering audit
    echo ""
    echo "Step 3/7: Hexagonal layering audit..."
    if python scripts/check_layering.py --strict; then
        print_success "Layering audit passed"
    else
        print_error "Layering audit failed"
        return 1
    fi

    # Step 4: Type checking (mypy), ratcheted against .claude/mypy-baseline.txt
    echo ""
    echo "Step 4/7: Type checking (baseline-ratcheted)..."
    local mypy_baseline
    mypy_baseline="$(grep -v '^#' .claude/mypy-baseline.txt | grep -v '^$' | head -1)"
    local mypy_errors
    mypy_errors="$(mypy src/modular_rag/ --no-error-summary 2>&1 | grep -c "error:" || true)"
    if [[ "$mypy_errors" -gt "$mypy_baseline" ]]; then
        print_error "Type checking: $mypy_errors errors, baseline is $mypy_baseline — new errors introduced"
        return 1
    else
        print_success "Type checking: $mypy_errors errors (baseline: $mypy_baseline)"
    fi

    # Step 5: Runnable-manifest validation (see manifests/README.md for the classification).
    # Every file under manifests/presets/ must wire cleanly (ADR-0007 Étape 7 exit criterion) —
    # fake-but-present secrets satisfy ${VAR}/secret:// interpolation for the wiring smoke test
    # without needing a real Postgres/Qdrant connection (components lazy-connect on first use).
    echo ""
    echo "Step 5/7: Runnable manifest validation (all manifests/presets/*.yaml)..."
    if QDRANT_URL="http://localhost:6333" QDRANT_API_KEY="smoke-test-key" AUDIT_DATABASE_URL="postgresql://smoke-test/db" python -c "
from pathlib import Path
from modular_rag.app.bootstrap import load_application

paths = sorted(Path('manifests/presets').glob('*.yaml')) + [Path('docker/local-hybrid-rag.yaml')]
for path in paths:
    application = load_application(str(path))
    print(f'{path.name} wires cleanly (engine={application.engine_name})')
    application.close()
"; then
        print_success "Runnable manifest validation passed"
    else
        print_error "Runnable manifest validation failed"
        return 1
    fi

    # Step 6: Unit tests (no external services)
    echo ""
    echo "Step 6/7: Running unit tests..."
    if pytest tests/unit/ -v --tb=short -q; then
        print_success "Unit tests passed"
    else
        print_error "Unit tests failed"
        return 1
    fi

    # Step 7: Contract tests (Protocol conformance)
    echo ""
    echo "Step 7/7: Running contract conformance tests..."
    if pytest tests/contract/ -v --tb=short -q; then
        print_success "Contract tests passed"
    else
        print_error "Contract tests failed"
        return 1
    fi

    print_success "Full check completed"
    echo ""
}

# ============================================================================
# INTEGRATION CHECK — With Qdrant (requires service running)
# Use: before merge, in CI/CD with services
# ============================================================================
check_integration() {
    print_header "INTEGRATION CHECK — With Qdrant (~1-2 min)"
    
    # Check if Qdrant is running
    if ! nc -z localhost 6333 2>/dev/null; then
        print_warning "Qdrant not available on localhost:6333 — skipping integration tests"
        print_warning "To run: docker run -p 6333:6333 qdrant/qdrant"
        return 0
    fi
    
    echo "Qdrant detected, running integration tests..."
    if pytest tests/integration/ -v --tb=short -q -m integration; then
        print_success "Integration tests passed"
    else
        print_error "Integration tests failed"
        return 1
    fi
    
    echo ""
}

# ============================================================================
# E2E CHECK — Full pipeline (requires Qdrant + LLM API key)
# Use: production verification, demos
# ============================================================================
check_e2e() {
    print_header "E2E CHECK — Full Pipeline (~2-5 min)"
    
    # Check prerequisites
    if ! nc -z localhost 6333 2>/dev/null; then
        print_error "Qdrant not running. Start with: docker run -p 6333:6333 qdrant/qdrant"
        return 1
    fi
    
    if [[ -z "${OPENAI_API_KEY:-}" ]] && [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
        print_error "No LLM API key set. Export OPENAI_API_KEY or ANTHROPIC_API_KEY"
        return 1
    fi
    
    echo "Running end-to-end pipeline tests..."
    if pytest tests/e2e/ -v --tb=short -q -m e2e; then
        print_success "E2E tests passed"
    else
        print_error "E2E tests failed"
        return 1
    fi
    
    echo ""
}

# ============================================================================
# ALL CHECK — All validations in sequence
# Use: before major releases, milestone verification
# ============================================================================
check_all() {
    print_header "COMPREHENSIVE CHECK — All validations"
    
    check_quick || return 1
    check_full || return 1
    check_integration || return 1
    check_e2e || return 1
    
    print_header "✓ ALL CHECKS PASSED"
}

# ============================================================================
# Help text
# ============================================================================
show_help() {
    cat << EOF
${BLUE}Modular RAG Framework — Validation Script${NC}

Usage: ./scripts/check.sh [COMMAND]

${BLUE}Commands:${NC}
  quick        Fast syntax & import check (~30s) — use daily
  full         Unit + contract tests (~2-5 min) — use pre-merge
  integration  With Qdrant integration (~1-2 min) — requires service
  e2e          Full pipeline tests (~2-5 min) — requires Qdrant + LLM key
  all          All validations in sequence — pre-release
  help         Show this help message

${BLUE}Examples:${NC}
  # Check after quick edit
  ./scripts/check.sh quick

  # Validate before merge
  ./scripts/check.sh full

  # Full validation with integration
  ./scripts/check.sh all

  # With Qdrant and API key
  export MRAG_OPENAI_API_KEY=sk-...
  docker run -p 6333:6333 qdrant/qdrant &
  ./scripts/check.sh all

${BLUE}Quick lookup:${NC}
  • quick  — ~30s   → syntax, imports, undefined names
  • full   — ~2-5m  → quick + unit tests + contracts
  • integ  — ~1-2m  → full + Qdrant integration tests
  • e2e    — ~2-5m  → integ + LLM pipeline tests
  • all    — ~10m   → all validation scopes

See CLAUDE.md block 04 for command reference.
See .claude/settings.json for permission model.
EOF
}

# ============================================================================
# Main entry point
# ============================================================================
main() {
    local mode="${1:-help}"
    
    case "$mode" in
        quick|q)
            check_quick || exit 1
            ;;
        full|f)
            check_full || exit 1
            ;;
        integration|i)
            check_integration || exit 1
            ;;
        e2e|e)
            check_e2e || exit 1
            ;;
        all|a)
            check_all || exit 1
            ;;
        help|h|-h|--help)
            show_help
            ;;
        *)
            print_error "Unknown command: $mode"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
