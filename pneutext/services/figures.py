"""Figures: images kept in the library's figures/ folder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pneutext.core.errors import NotFound
from pneutext.store import db
from pneutext.store import figures as figures_store
from pneutext.store.figures import FigureRow
from pneutext.store.library import Library


@dataclass(frozen=True)
class FigureView:
    figure: FigureRow
    has_file: bool


def _path(library: Library, figure: FigureRow) -> Path | None:
    """The figure's image file, if it is present and really inside the figures folder."""
    root = library.figures_dir.resolve()
    path = (root / figure.file).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None


def list_figures(library: Library) -> list[FigureView]:
    with db.transaction(library.db_path) as conn:
        rows = figures_store.list_figures(conn)
    return [FigureView(row, _path(library, row) is not None) for row in rows]


def figure_file(library: Library, label: str) -> Path:
    with db.transaction(library.db_path) as conn:
        figure = figures_store.get_figure(conn, label)
    path = None if figure is None else _path(library, figure)
    if path is None:
        raise NotFound("That figure has no image file.")
    return path
