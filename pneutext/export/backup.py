"""The backup writer: the whole library as JSON, plus its figures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

FORMAT = "pneutext-backup-1"


def write_backup(
    tables: dict[str, list[dict[str, Any]]],
    figures_dir: Path,
    folder: Path,
    includes_text: bool,
    schema_version: int,
) -> list[str]:
    """Write ``library.json`` and a ``figures/`` folder. Returns the paths written."""
    folder.mkdir(parents=True, exist_ok=True)
    document = {
        "format": FORMAT,
        "schema_version": schema_version,
        "includes_corpus_text": includes_text,
        "tables": tables,
    }
    (folder / "library.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    written = ["library.json"]
    target = folder / "figures"
    if target.is_dir():
        shutil.rmtree(target)
    target.mkdir()
    if figures_dir.is_dir():
        for source in sorted(figures_dir.iterdir()):
            if source.is_file():
                shutil.copyfile(source, target / source.name)
                written.append(f"figures/{source.name}")
    return written
