"""The ``pneutext`` command: start the local server and open the browser."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

from pneutext.api.app import create_app
from pneutext.store.library import DEFAULT_LIBRARY_DIR, open_library

HOST = "127.0.0.1"  # PneuText is local only; it never listens on another interface.
DEFAULT_PORT = 8765


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pneutext", description="Start PneuText and open it in the browser."
    )
    parser.add_argument(
        "--library",
        type=Path,
        default=DEFAULT_LIBRARY_DIR,
        metavar="DIR",
        help="library folder (default: ~/.pneutext)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, metavar="N")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    library = open_library(args.library)
    app = create_app(library)
    url = f"http://{HOST}:{args.port}/"
    print(f"PneuText: library at {library.root}, serving {url}")
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
