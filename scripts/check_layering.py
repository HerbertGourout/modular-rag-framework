"""Check Modular RAG import boundaries.

This script is intentionally lightweight: it parses Python imports with `ast`
and reports project-internal imports that violate the repository's hexagonal
layering rules documented in CLAUDE.md.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "modular_rag"
BASELINE_PATH = PROJECT_ROOT / ".claude" / "layering-baseline.txt"

DOMAIN_LAYERS = {
    "agents",
    "eval",
    "generation",
    "ingestion",
    "memory",
    "retrieval",
    "security",
}

SELF_ONLY_LAYERS = {"core"}
CONTRACT_LAYERS = {"contracts"}
ADAPTER_LAYERS = {"adapters"}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    importer_layer: str
    imported_module: str
    reason: str

    def key(self) -> str:
        rel_path = self.path.relative_to(PROJECT_ROOT).as_posix()
        return f"{rel_path}|{self.importer_layer}|{self.imported_module}|{self.reason}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Modular RAG import boundaries.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on all violations, including entries listed in the baseline.",
    )
    parser.add_argument(
        "--show-baseline",
        action="store_true",
        help="Print baseline violations even when they are accepted.",
    )
    args = parser.parse_args()

    violations: list[Violation] = []

    for path in sorted(SRC_ROOT.rglob("*.py")):
        importer_layer = _top_layer(path)
        if importer_layer is None:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported = _imported_module(node)
            if imported is None or not imported.startswith("modular_rag."):
                continue

            reason = _violation_reason(importer_layer, imported)
            if reason:
                violations.append(
                    Violation(
                        path=path,
                        line=getattr(node, "lineno", 1),
                        importer_layer=importer_layer,
                        imported_module=imported,
                        reason=reason,
                    )
                )

    baseline = _load_baseline()
    active_violations = violations if args.strict else [v for v in violations if v.key() not in baseline]
    baseline_violations = [] if args.strict else [v for v in violations if v.key() in baseline]

    if not active_violations:
        print("Layering check passed.")
        if baseline_violations:
            print(f"Accepted baseline violations: {len(baseline_violations)}")
            if args.show_baseline:
                _print_violations(baseline_violations)
        return 0

    print("Layering violations found:")
    _print_violations(active_violations)
    if baseline_violations:
        print(f"Accepted baseline violations not shown: {len(baseline_violations)}")
    return 1


def _print_violations(violations: list[Violation]) -> None:
    for violation in violations:
        rel_path = violation.path.relative_to(PROJECT_ROOT)
        print(
            f"{rel_path}:{violation.line}: "
            f"{violation.importer_layer} imports {violation.imported_module} "
            f"({violation.reason})"
        )


def _load_baseline() -> set[str]:
    if not BASELINE_PATH.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _top_layer(path: Path) -> str | None:
    relative = path.relative_to(SRC_ROOT)
    if not relative.parts:
        return None
    return relative.parts[0]


def _imported_module(node: ast.AST) -> str | None:
    if isinstance(node, ast.ImportFrom):
        return node.module
    if isinstance(node, ast.Import) and node.names:
        return node.names[0].name
    return None


def _violation_reason(importer_layer: str, imported_module: str) -> str | None:
    imported_layer = _imported_layer(imported_module)
    if imported_layer is None:
        return None

    if importer_layer in SELF_ONLY_LAYERS:
        if imported_layer != importer_layer:
            return "core can only import core modules"
        return None

    if importer_layer in CONTRACT_LAYERS:
        if imported_layer not in {"core", "contracts"}:
            return "contracts can only import core or contracts modules"
        return None

    if importer_layer in ADAPTER_LAYERS:
        if imported_layer not in {"core", "contracts", "adapters"}:
            return "adapters cannot import domain modules"
        return None

    if importer_layer in DOMAIN_LAYERS:
        if imported_layer not in {"core", "contracts", importer_layer}:
            return "domain modules cannot import other domain modules"
        return None

    return None


def _imported_layer(imported_module: str) -> str | None:
    parts = imported_module.split(".")
    if len(parts) < 2 or parts[0] != "modular_rag":
        return None
    return parts[1]


if __name__ == "__main__":
    raise SystemExit(main())
