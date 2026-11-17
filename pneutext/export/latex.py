"""The monograph writer: a LaTeX project from an ``ExportBook``.

Writes a main file, one file per chapter, PneuText's own style file and a ``figures/``
folder. Output is deterministic: the same book produces byte-identical source.

Every piece of text that reaches the output passes through ``escape``; note text can
never inject LaTeX commands. This module is given page shapes and notes only. It has no
access to the corpus.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined

from pneutext.core.shape import DrawnLine
from pneutext.export.model import (
    ExportBook,
    ExportChapter,
    ExportFigure,
    ExportNote,
    ExportPage,
    Tree,
)

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "|": r"\textbar{}",
    '"': r"\textquotedbl{}",
}

# Row heights on a facsimile, in lines: a chapter number stands two lines tall.
_ROW_HEIGHT = {"chapter_number": 2.0}
# Images LaTeX can include as they are.
_INCLUDABLE = {".png", ".jpg", ".jpeg", ".pdf"}


def escape(text: str) -> str:
    """Make any text safe to place in LaTeX source. The one escaping function."""
    out = []
    for character in text:
        if character in _ESCAPES:
            out.append(_ESCAPES[character])
        elif character == "\n":
            out.append(" ")
        elif ord(character) < 32 or ord(character) == 127:
            continue  # control characters have no business in a book
        else:
            out.append(character)
    return "".join(out)


def escape_url(url: str) -> str:
    """A web address for ``\\href``: the characters LaTeX would act on are escaped."""
    return "".join("\\" + c if c in "\\{}%#&_~^$" else c for c in url if c >= " ")


def _number(value: float, places: int) -> str:
    """A coordinate, written the same way every time."""
    text = f"{value:.{places}f}"
    return "0." + "0" * places if text.startswith("-0.") and float(text) == 0 else text


@dataclass(frozen=True)
class _Context:
    book: ExportBook
    figure_numbers: dict[str, ExportFigure]  # by label, for figures placed in this edition


def _children(node: Tree, context: _Context) -> str:
    return "".join(_inline(child, context) for child in node.get("children") or [])


def _citation(attrs: dict[str, object]) -> str:
    """A page citation in words: ``p. 45.12`` (the label the resolver made)."""
    return escape(str(attrs.get("label") or "")).replace("p. ", "p.~")


def _inline(node: Tree, context: _Context) -> str:
    """One inline node as LaTeX."""
    kind = node["type"]
    attrs: dict[str, object] = node.get("attrs") or {}
    if kind == "text":
        return escape(node.get("text") or "")
    if kind == "emphasis":
        return r"\emph{" + _children(node, context) + "}"
    if kind == "strong":
        return r"\textbf{" + _children(node, context) + "}"
    if kind == "code":
        return r"\texttt{" + escape(node.get("text") or "") + "}"
    if kind == "softbreak":
        return " "
    if kind == "hardbreak":
        return "\\\\\n"
    if kind == "link":
        href = str(attrs.get("href") or "")
        text = _children(node, context)
        if href.lower().startswith(("http://", "https://", "mailto:")):
            return r"\href{" + escape_url(href) + "}{" + text + "}"
        return text
    if kind == "image":
        return "[" + escape(str(attrs.get("alt") or "image")) + "]"
    if kind == "reference":
        if attrs.get("broken") is not False:
            return escape(node.get("text") or "")
        page = attrs.get("page")
        text = _citation(attrs)
        # A citation links to the page's facsimile when this edition has one.
        if isinstance(page, int) and page in context.book.pages:
            return rf"\pneupageref{{{page}}}{{{text}}}"
        return text
    if kind == "note_ref":
        target = attrs.get("id")
        page = attrs.get("page")
        if attrs.get("broken") is not False or not isinstance(target, int):
            return escape(node.get("text") or "")
        placed = context.book.numbers.get(target)
        if placed is None:
            # The note is not part of this edition: cite its page and nothing more.
            return f"p.~{page}" if isinstance(page, int) else ""
        return rf"\pneunoteref{{{target}}}{{p.~{placed[0]}, note~{placed[1]}}}"
    if kind == "figure_ref":
        figure = context.figure_numbers.get(str(attrs.get("label") or ""))
        if figure is not None:
            return rf"\pneufigureref{{{figure.number}}}"
        if attrs.get("broken") is False:
            return escape(str(attrs.get("caption") or attrs.get("label") or ""))
        return escape(node.get("text") or "")
    if kind == "gloss":
        word, meaning = (
            escape(str(attrs.get("word") or "")),
            escape(str(attrs.get("meaning") or "")),
        )
        return rf"\pneugloss{{{word}}}{{{meaning}}}" if meaning else rf"\emph{{{word}}}"
    if kind in ("when", "since"):
        value = attrs.get("value")
        return escape(str(value)) if isinstance(value, str) else escape(node.get("text") or "")
    if kind == "figure":
        return _figure(attrs, context)
    # Anything else (a form not understood, a citation not yet supported) keeps its words.
    if node.get("children"):
        return _children(node, context)
    return escape(node.get("text") or "")


def _figure(attrs: dict[str, object], context: _Context) -> str:
    figure = context.figure_numbers.get(str(attrs.get("label") or ""))
    if figure is None:
        return escape(str(attrs.get("caption") or ""))
    caption, credit = escape(figure.caption), escape(figure.credit)
    if figure.file is None:
        return rf"\pneufiguremissing{{{figure.number}}}{{{caption}}}{{{credit}}}"
    return rf"\pneufigure{{{figure.number}}}{{figures/{figure.file}}}{{{caption}}}{{{credit}}}"


def _blocks(node: Tree, context: _Context) -> list[str]:
    """A container's children as LaTeX blocks. Editorial remarks are left out."""
    out: list[str] = []
    for child in node.get("children") or []:
        block = _block(child, context)
        if block:
            out.append(block)
    return out


def _block(node: Tree, context: _Context) -> str:
    kind = node["type"]
    attrs: dict[str, object] = node.get("attrs") or {}
    if kind == "todo":
        return ""  # TODO remarks never appear in an export
    if kind == "paragraph":
        return _children(node, context).strip()
    if kind == "heading":
        return r"\subsubsection*{" + _children(node, context) + "}"
    if kind == "blockquote":
        return "\\begin{quote}\n" + "\n\n".join(_blocks(node, context)) + "\n\\end{quote}"
    if kind in ("bullet_list", "ordered_list"):
        name = "itemize" if kind == "bullet_list" else "enumerate"
        items = [
            "\\item " + "\n\n".join(_blocks(item, context)) for item in node.get("children") or []
        ]
        start = attrs.get("start")
        counter = (
            f"\\setcounter{{enumi}}{{{int(start) - 1}}}\n"
            if kind == "ordered_list" and isinstance(start, int) and start != 1
            else ""
        )
        return f"\\begin{{{name}}}\n{counter}" + "\n".join(items) + f"\n\\end{{{name}}}"
    if kind == "code_block":
        lines = (node.get("text") or "").rstrip("\n").split("\n")
        body = "\\\\\n".join(escape(line).replace(" ", "~") for line in lines)
        return "\\begin{quote}\\ttfamily\n" + body + "\n\\end{quote}"
    if kind == "thematic_break":
        return r"\par\medskip\noindent\hrulefill\par\medskip"
    return _inline(node, context).strip()


def render_body(body: Tree, context: _Context) -> str:
    """A note body as LaTeX: its blocks, a blank line between each."""
    return "\n\n".join(_blocks(body, context))


def _inline_body(body: Tree, context: _Context) -> str:
    """A note body on one line, for a chapter title or a glossary entry."""
    return " ".join(part.replace("\n\n", " ") for part in _blocks(body, context))


# ---- Page facsimiles ----------------------------------------------------------


def _facsimile(page: ExportPage) -> list[str]:
    """A print page drawn blank, from its shape: bars, highlight bands, numbered markers."""
    rows: list[tuple[float, DrawnLine]] = []
    y = 0.0
    for line in page.lines:
        rows.append((y, line))
        y += _ROW_HEIGHT.get(line.kind, 1.0)

    out = [rf"\begin{{pneupage}}{{{page.page}}}{{{_number(y, 2)}}}"]
    for top, line in rows:
        where = _number(top, 2)
        if line.kind == "chapter_number":
            out.append(rf"  \pneuchapternumber{{{where}}}")
        elif line.kind == "ornament":
            out.append(rf"  \pneuornament{{{where}}}")
        elif line.kind == "rule":
            out.append(rf"  \pneurule{{{where}}}")
        else:
            out.append(rf"  \pneubar{{{where}}}{{{_number(line.x0, 4)}}}{{{_number(line.x1, 4)}}}")
            for mark in line.highlights:
                # Overlapping highlights stack as bands within the bar's height.
                slice_height = 0.5 / max(line.bands, 1)
                y0 = top + mark.band * slice_height
                out.append(
                    rf"  \pneuhl{{{_number(y0, 3)}}}{{{_number(y0 + slice_height, 3)}}}"
                    rf"{{{_number(mark.x0, 4)}}}{{{_number(mark.x1, 4)}}}{{pneutype{mark.type_id}}}"
                )
    for marker in page.markers:
        top = rows[marker.line][0]
        out.append(
            rf"  \pneumark{{{_number(top, 2)}}}{{{_number(marker.x, 4)}}}{{{marker.number}}}"
        )
    out.append(r"\end{pneupage}")
    return out


def _note(note: ExportNote, context: _Context) -> list[str]:
    head = rf"\pneunote{{{note.number}}}{{{escape(note.type_name)}}}{{{note.level}}}{{{note.id}}}"
    body = render_body(note.body, context)
    return [head, body] if body else [head]


def render_chapter(chapter: ExportChapter, context: _Context) -> str:
    """One chapter's file."""
    out: list[str] = []
    if chapter.label:
        out.append(rf"\pneuchapter{{{escape(chapter.label)}}}")
    if chapter.title is not None:
        out.append(rf"\pneuchaptertitle{{{_inline_body(chapter.title, context)}}}")
    if chapter.summary is not None:
        out += [
            r"\begin{pneuchaptersummary}",
            render_body(chapter.summary, context),
            r"\end{pneuchaptersummary}",
        ]
    if chapter.notes:
        out.append(r"\begin{pneuchapternotes}")
        for note in chapter.notes:
            out += _note(note, context)
        out.append(r"\end{pneuchapternotes}")
    for page in chapter.pages:
        out.append("")
        out += _facsimile(page)
        out.append("")
        out.append(rf"\begin{{pneunotes}}{{{page.page}}}")
        for note in page.notes:
            out += ["", *_note(note, context)]
        out.append(r"\end{pneunotes}")
    return "\n".join(out).strip("\n") + "\n"


# ---- Glossary, indexes, list of figures ------------------------------------------


def _note_citation(note: ExportNote) -> str:
    return rf"\pneunoteref{{{note.id}}}{{p.~{note.page}, note~{note.number}}}"


def _glossary_lines(book: ExportBook, context: _Context) -> list[str]:
    lines = []
    for entry in book.glossary:
        definition = _inline_body(_without_term(entry.note.body), context)
        lines.append(
            rf"\pneuglossaryentry{{{escape(entry.term)}}}{{{definition}}}{{{_note_citation(entry.note)}}}"
        )
    return lines


def _without_term(body: Tree) -> Tree:
    """A definition's body without its leading **term** and the dash after it."""
    blocks = list(body.get("children") or [])
    if not blocks or blocks[0].get("type") != "paragraph":
        return body
    inline = list(blocks[0].get("children") or [])
    if not inline or inline[0].get("type") != "strong":
        return body
    rest = inline[1:]
    if rest and rest[0].get("type") == "text":
        text = str(rest[0].get("text") or "").lstrip()
        text = text[1:].lstrip() if text[:1] in ("-", "\u2013", "\u2014", ":") else text
        rest = [{"type": "text", "text": text}, *rest[1:]]
    return {**body, "children": [{**blocks[0], "children": rest}, *blocks[1:]]}


def _page_list(pages: list[int], book: ExportBook) -> str:
    """Print pages, each linked to its facsimile when there is one."""
    seen = sorted(set(pages))
    return ", ".join(
        rf"\pneupageref{{{page}}}{{{page}}}" if page in book.pages else str(page) for page in seen
    )


# ---- The project -------------------------------------------------------------------


def _environment() -> Environment:
    environment = Environment(
        loader=PackageLoader("pneutext.export", "templates"),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        # LaTeX is full of braces, so the template's own marks are parentheses.
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((#",
        comment_end_string="#))",
    )
    environment.filters["tex"] = escape
    return environment


def render_project(book: ExportBook) -> dict[str, str]:
    """Every text file of the project, by its path within the export folder."""
    context = _Context(book, {figure.label: figure for figure in book.figures})
    files: dict[str, str] = {}
    for chapter in book.chapters:
        files[f"chapters/chapter-{chapter.key}.tex"] = render_chapter(chapter, context)

    indexes = [
        {
            "category": index.category,
            "lines": [
                rf"\pneuindexentry{{{escape(entry.name)}"
                + (f" ({escape(entry.value)})" if entry.value else "")
                + rf"}}{{{_page_list(entry.pages, book)}}}"
                for entry in index.entries
            ],
        }
        for index in book.indexes
        if index.entries
    ]
    figures = [
        rf"\pneufigureentry{{{figure.number}}}{{{escape(figure.caption)}}}"
        rf"{{{_page_list([figure.page], book)}}}"
        for figure in book.figures
    ]
    files["main.tex"] = (
        _environment()
        .get_template("main.tex.j2")
        .render(
            book=book,
            glossary=_glossary_lines(book, context),
            indexes=indexes,
            figures=figures,
        )
    )
    style = resources.files("pneutext.export").joinpath("pneutext.sty")
    files["pneutext.sty"] = style.read_text(encoding="utf-8")
    return files


def write_project(book: ExportBook, folder: Path) -> list[str]:
    """Write the project into a folder, replacing what an earlier export left there.

    Returns the paths written, relative to the folder, in a fixed order.
    """
    files = render_project(book)
    folder.mkdir(parents=True, exist_ok=True)
    # Clear what this exporter owns, so nothing stale survives a change of edition.
    for owned in (folder / "chapters", folder / "figures"):
        if owned.is_dir():
            shutil.rmtree(owned)
    (folder / "chapters").mkdir()
    (folder / "figures").mkdir()

    written: list[str] = []
    for path in sorted(files):
        target = folder / path
        target.write_text(files[path], encoding="utf-8", newline="\n")
        written.append(path)
    for figure in book.figures:
        if figure.file is not None and figure.source is not None:
            shutil.copyfile(figure.source, folder / "figures" / figure.file)
            written.append(f"figures/{figure.file}")
    return written


def includable(file_name: str) -> bool:
    """Whether LaTeX can include an image of this kind as it is."""
    return Path(file_name).suffix.lower() in _INCLUDABLE
