"""Figures: images kept in the library's figures/ folder, placed in and cited from notes."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pneutext import notes as note_parser
from pneutext.core.errors import Conflict, InvalidInput, NotFound
from pneutext.store import corpus as corpus_store
from pneutext.store import db
from pneutext.store import figures as figures_store
from pneutext.store import notes as notes_store
from pneutext.store.figures import FigureRow
from pneutext.store.library import Library

_LABEL = re.compile(r"[a-z0-9][a-z0-9-]*")
IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/tiff": ".tif",
}
MAX_IMAGE_BYTES = 40 * 1024 * 1024


@dataclass(frozen=True)
class FigureUse:
    """A note that places or cites a figure."""

    note_id: int
    type_id: int
    version_id: int
    page: int | None
    line_no: int | None
    placed: bool  # placed here with ![..](fig:..), as opposed to referred to


@dataclass(frozen=True)
class FigureView:
    figure: FigureRow
    has_file: bool
    uses: list[FigureUse]


def _path(library: Library, figure: FigureRow) -> Path | None:
    """The figure's image file, if it is present and really inside the figures folder."""
    if not figure.file:
        return None
    root = library.figures_dir.resolve()
    path = (root / figure.file).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None


def _walk(node: note_parser.Node) -> list[note_parser.Node]:
    found = [node]
    for child in node.get("children", []):
        found.extend(_walk(child))
    return found


def _uses(conn: sqlite3.Connection, label: str) -> list[FigureUse]:
    """Every note whose body places or cites the figure with this label."""
    out: list[FigureUse] = []
    versions = corpus_store.list_versions(conn)
    for version in versions:
        for note in notes_store.find_notes(conn, version.id, body_like=f"%fig:{label}%"):
            kinds = {
                node["type"]
                for node in _walk(note_parser.parse(note.body_md))
                if node["type"] in ("figure", "figure_ref")
                and (node.get("attrs") or {}).get("label") == label
            }
            if not kinds:
                continue
            located = notes_store.locate(
                conn, version.pagination_id, note.anchor.start_segment_id, note.anchor.start_offset
            )
            page, line = located if located is not None else (None, None)
            out.append(FigureUse(note.id, note.type_id, version.id, page, line, "figure" in kinds))
    return out


def _view(conn: sqlite3.Connection, library: Library, figure: FigureRow) -> FigureView:
    return FigureView(figure, _path(library, figure) is not None, _uses(conn, figure.label))


def list_figures(library: Library) -> list[FigureView]:
    with db.transaction(library.db_path) as conn:
        return [_view(conn, library, row) for row in figures_store.list_figures(conn)]


def figure_file(library: Library, label: str) -> Path:
    with db.transaction(library.db_path) as conn:
        figure = figures_store.get_figure(conn, label)
    path = None if figure is None else _path(library, figure)
    if path is None:
        raise NotFound("That figure has no image file.")
    return path


def _check_label(conn: sqlite3.Connection, label: str, except_id: int | None) -> str:
    label = label.strip()
    if not _LABEL.fullmatch(label):
        raise InvalidInput(
            "A figure's label is lower-case letters, digits and hyphens, such as tang."
        )
    existing = figures_store.get_figure(conn, label)
    if existing is not None and existing.id != except_id:
        raise Conflict(f"Another figure is already labeled {label}.")
    return label


def _require(conn: sqlite3.Connection, figure_id: int) -> FigureRow:
    figure = figures_store.get_figure_by_id(conn, figure_id)
    if figure is None:
        raise NotFound("That figure no longer exists.")
    return figure


def create_figure(library: Library, label: str, caption: str, credit: str) -> FigureView:
    with db.transaction(library.db_path) as conn:
        label = _check_label(conn, label, None)
        figure_id = figures_store.insert_figure(conn, label, "", caption.strip(), credit.strip())
        return _view(conn, library, _require(conn, figure_id))


def update_figure(
    library: Library,
    figure_id: int,
    label: str | None = None,
    caption: str | None = None,
    credit: str | None = None,
) -> FigureView:
    """Edit a figure. Changing its label rewrites the notes that place or cite it."""
    with db.transaction(library.db_path) as conn:
        figure = _require(conn, figure_id)
        new_label = figure.label if label is None else _check_label(conn, label, figure.id)
        if new_label != figure.label:
            _relabel_in_notes(conn, figure.label, new_label)
        figures_store.update_figure(
            conn,
            figure.id,
            new_label,
            figure.file,
            figure.caption if caption is None else caption.strip(),
            figure.credit if credit is None else credit.strip(),
        )
        return _view(conn, library, _require(conn, figure.id))


def _relabel_in_notes(conn: sqlite3.Connection, old: str, new: str) -> None:
    """Follow a figure's new label in every note that places or cites it."""
    placed = re.compile(rf"\]\(fig:{re.escape(old)}\)")
    cited = re.compile(rf"\{{\{{\s*fig\s*:\s*{re.escape(old)}\s*\}}\}}")
    for version in corpus_store.list_versions(conn):
        for note in notes_store.find_notes(conn, version.id, body_like=f"%fig:{old}%"):
            body = placed.sub(f"](fig:{new})", note.body_md)
            body = cited.sub("{{fig:" + new + "}}", body)
            if body != note.body_md:
                notes_store.update_annotation(conn, note.id, {"body_md": body})


def delete_figure(library: Library, figure_id: int) -> None:
    """Remove a figure and its image. Notes that used it keep their reference, now broken."""
    with db.transaction(library.db_path) as conn:
        figure = _require(conn, figure_id)
        path = _path(library, figure)
        figures_store.delete_figure(conn, figure.id)
    if path is not None:
        path.unlink(missing_ok=True)


def save_image(library: Library, figure_id: int, content_type: str, data: bytes) -> FigureView:
    """Store an uploaded image as the figure's file."""
    extension = IMAGE_TYPES.get(content_type.split(";")[0].strip().lower())
    if extension is None:
        raise InvalidInput(
            "That file is not an image PneuText can use (PNG, JPEG, GIF, WebP, SVG, TIFF)."
        )
    if not data:
        raise InvalidInput("The file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise InvalidInput("The image is larger than 40 MB.")
    with db.transaction(library.db_path) as conn:
        figure = _require(conn, figure_id)
        library.figures_dir.mkdir(exist_ok=True)
        old = _path(library, figure)
        file_name = figure.label + extension
        (library.figures_dir / file_name).write_bytes(data)
        if old is not None and old.name != file_name:
            old.unlink(missing_ok=True)
        figures_store.update_figure(
            conn, figure.id, figure.label, file_name, figure.caption, figure.credit
        )
        return _view(conn, library, _require(conn, figure.id))
