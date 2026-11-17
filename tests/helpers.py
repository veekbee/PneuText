from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pneutext.core.corpus import ParsedCorpus
from pneutext.importers.paged_corpus import PageSource

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BOOK = FIXTURES / "book"
GOLDEN = FIXTURES / "golden"


def page(number: int, text: str) -> PageSource:
    return PageSource(number, f"T_corp_p{number:03d}.txt", text.encode("utf-8"))


def corpus_as_json(corpus: ParsedCorpus) -> dict[str, Any]:
    return {
        "pages": corpus.pages,
        "summary": asdict(corpus.summary()),
        "segments": [asdict(segment) for segment in corpus.segments],
        "divisions": [asdict(division) for division in corpus.divisions],
        "problems": [asdict(problem) for problem in corpus.problems],
    }


def assert_matches_golden(name: str, actual: object) -> None:
    """Compare with a checked-in golden file. Set PNEUTEXT_UPDATE_GOLDEN=1 to rewrite it."""
    path = GOLDEN / name
    rendered = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if os.environ.get("PNEUTEXT_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == rendered, f"{name} differs from its golden file"
