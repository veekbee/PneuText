"""Write the API's OpenAPI schema as JSON, for generating the front end's types.

Usage: ``python -m pneutext.api.openapi OUTPUT.json``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pneutext.api.app import create_app
from pneutext.store.library import Library


def build_schema() -> dict[str, Any]:
    # The schema depends only on the routes, so no real library is opened.
    return create_app(Library(Path("unused")), web_dist=None).openapi()


def render_schema() -> str:
    return json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(render_schema(), encoding="utf-8")
