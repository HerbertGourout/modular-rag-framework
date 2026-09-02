#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

if [ ! -f ".githooks/pre-push" ]; then
    echo "Missing versioned hook: .githooks/pre-push" >&2
    exit 1
fi

chmod +x .githooks/pre-push
git config core.hooksPath .githooks
echo "Git hooks installed for this clone (core.hooksPath=.githooks)."
echo "Every git push now runs scripts/check_docs.py and stops on documentation drift."
