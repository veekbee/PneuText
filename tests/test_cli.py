from __future__ import annotations

from pathlib import Path

from pneutext import cli
from pneutext.store.library import DEFAULT_LIBRARY_DIR


def test_defaults() -> None:
    args = cli.build_parser().parse_args([])
    assert args.library == DEFAULT_LIBRARY_DIR
    assert args.port == cli.DEFAULT_PORT
    assert args.no_browser is False


def test_library_and_port_options() -> None:
    args = cli.build_parser().parse_args(["--library", "/tmp/lib", "--port", "9000"])
    assert args.library == Path("/tmp/lib")
    assert args.port == 9000


def test_server_binds_to_loopback_only() -> None:
    assert cli.HOST == "127.0.0.1"
