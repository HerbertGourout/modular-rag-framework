"""Prepare a deterministic SQuAD 1.1 sample for the offline benchmark.

The generated YAML is an experiment artifact, not a framework golden-set
fixture. It keeps one paragraph as one stable corpus chunk and uses the first
annotated answer for each selected question.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "untitled"


def prepare(input_path: Path, output_path: Path, limit: int) -> None:
    raw: dict[str, Any] = json.loads(input_path.read_text(encoding="utf-8"))
    corpus: list[dict[str, str]] = []
    cases: list[dict[str, Any]] = []
    seen_chunks: set[str] = set()

    for article in raw["data"]:
        article_slug = _slug(article["title"])
        for paragraph_index, paragraph in enumerate(article["paragraphs"]):
            chunk_id = f"squad-{article_slug}-{paragraph_index}"
            if chunk_id not in seen_chunks:
                corpus.append(
                    {
                        "chunk_id": chunk_id,
                        "doc_id": f"squad-{article_slug}",
                        "content": paragraph["context"],
                    }
                )
                seen_chunks.add(chunk_id)

            for question in paragraph["qas"]:
                answers = question.get("answers", [])
                if not answers:
                    continue
                cases.append(
                    {
                        "case_type": "qa",
                        "question": question["question"],
                        "expected_answer": answers[0]["text"],
                        "relevant_chunk_ids": [chunk_id],
                    }
                )
                if len(cases) >= limit:
                    output = {
                        "schema_version": "1.0",
                        "name": f"squad-v1-sample-{limit}",
                        "domain": "general-qa",
                        "corpus": corpus,
                        "cases": cases,
                    }
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(
                        yaml.safe_dump(output, allow_unicode=False, sort_keys=False),
                        encoding="utf-8",
                    )
                    return

    raise ValueError(f"Dataset contains only {len(cases)} answerable cases; requested {limit}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be positive")
    prepare(args.input, args.output, args.limit)
    print(f"Prepared {args.output} with {args.limit} QA cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
