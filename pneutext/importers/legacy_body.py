"""Converting a legacy note body to PneuText's note syntax. Pure: no I/O.

Handles page-reference, figure, gloss and figure-reference commands, editorial remarks,
and common LaTeX formatting. What each LaTeX command means is configuration
(``BodyFormat``); a command it does not know is left in place and reported by name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_DEFINITION = re.compile(r"\*\*(?P<term>[^*\n]+)\*\*\s+-\s+(?P<meaning>\S.*)", re.DOTALL)
_COMMAND = re.compile(r"\\([A-Za-z]+)")
_REMARK_LEAD = re.compile(r"^XXX\b[:\s]*")
_LABEL_JUNK = re.compile(r"[^a-z0-9]+")


def _default_latex() -> dict[str, tuple[int, str]]:
    # name -> (number of {arguments}, replacement with {0}, {1}... for the arguments)
    return {
        "textbf": (1, "**{0}**"),
        "textit": (1, "*{0}*"),
        "emph": (1, "*{0}*"),
        "textsc": (1, "{0}"),
        "textemdash": (0, "\u2014"),
        "textendash": (0, "\u2013"),
        "ldots": (0, "\u2026"),
        "dots": (0, "\u2026"),
    }


@dataclass(frozen=True)
class BodyFormat:
    """How to read legacy note bodies."""

    work_code: str = ""
    page_ref_commands: tuple[str, ...] = ()  # e.g. a macro that cites a page of the work
    gloss_commands: tuple[str, ...] = ("spanish",)
    figure_ref_commands: tuple[str, ...] = ("reffig",)
    latex: dict[str, tuple[int, str]] = field(default_factory=_default_latex)
    figure_extensions: tuple[str, ...] = ("png", "jpg", "jpeg", "gif", "webp", "svg", "tif", "tiff")

    def commands(self) -> dict[str, tuple[int, str]]:
        table = dict(self.latex)
        table.update(
            {name: (1, "{{{{" + self.work_code + ":{0}}}}}") for name in self.page_ref_commands}
        )
        table.update({name: (2, "{{{{gloss:{0}|{1}}}}}") for name in self.gloss_commands})
        table.update({name: (1, "{{{{fig:{0}}}}}") for name in self.figure_ref_commands})
        return table


@dataclass(frozen=True)
class FigureUse:
    label: str
    file: str
    caption: str
    line: int  # line within the body, counting from 0


@dataclass(frozen=True)
class BodyProblem:
    code: str
    tag: str
    line: int  # line within the body, counting from 0


@dataclass(frozen=True)
class ConvertedBody:
    markdown: str
    figures: list[FigureUse]
    problems: list[BodyProblem]
    is_definition: bool


def figure_label(file_name: str) -> str:
    """A figure's label, from its file name: ``Low Harbor.JPG`` becomes ``low-harbor``."""
    stem = file_name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return _LABEL_JUNK.sub("-", stem.lower()).strip("-") or "figure"


_COMMENT_MARK = "\x00"  # marks a line that was a % comment, until it gets its own paragraph


def convert(body: str, fmt: BodyFormat) -> ConvertedBody:
    # Remarks are rewritten line for line first, so the line numbers that problems are
    # reported with still match the body as it was written.
    text = "\n".join(_remarks(body.strip("\n").split("\n")))
    problems: list[BodyProblem] = []
    figures: list[FigureUse] = []
    text = _figures(text, fmt, figures)
    text = _latex(text, fmt.commands(), problems)
    text = text.replace("``", "\u201c").replace("''", "\u201d")
    text = "\n".join(_own_paragraphs(text.split("\n")))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return ConvertedBody(text, figures, problems, _DEFINITION.fullmatch(text) is not None)


def _remarks(lines: list[str]) -> list[str]:
    """Turn ``XXX`` paragraphs and ``%`` comment lines into ``TODO:`` remarks, line for line."""
    out: list[str] = []
    paragraph_start = True
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("%"):
            out.append(_COMMENT_MARK + "TODO: " + stripped.lstrip("%").strip())
        elif paragraph_start and _REMARK_LEAD.match(stripped):
            out.append("TODO: " + _REMARK_LEAD.sub("", stripped))
        else:
            out.append(line)
        paragraph_start = stripped == ""
    return out


def _own_paragraphs(lines: list[str]) -> list[str]:
    """Set each former comment line apart as a paragraph of its own."""
    out: list[str] = []
    for line in lines:
        if line.startswith(_COMMENT_MARK):
            out += ["", line[len(_COMMENT_MARK) :], ""]
        else:
            out.append(line)
    return out


def _figures(text: str, fmt: BodyFormat, found: list[FigureUse]) -> str:
    extensions = "|".join(re.escape(ext) for ext in fmt.figure_extensions)
    file_name = rf"[^\[\]()\n]+\.(?:{extensions})"
    patterns = [
        re.compile(rf"!?\((?P<caption>[^()\n]*)\)\[(?P<file>{file_name})\]", re.IGNORECASE),
        re.compile(rf"!?\[(?P<caption>[^\[\]\n]*)\]\((?P<file>{file_name})\)", re.IGNORECASE),
    ]

    def replace(match: re.Match[str]) -> str:
        file = match.group("file").strip()
        if "://" in file or file.startswith("fig:"):
            return match.group(0)  # a web link or an already converted figure, not a file
        caption = match.group("caption").strip()
        label = figure_label(file)
        found.append(FigureUse(label, file, caption, text.count("\n", 0, match.start())))
        return f"![{caption}](fig:{label})"

    for pattern in patterns:
        text = pattern.sub(replace, text)
    found.sort(key=lambda figure: figure.line)
    return text


def _latex(text: str, commands: dict[str, tuple[int, str]], problems: list[BodyProblem]) -> str:
    """Replace known LaTeX commands; leave unknown ones in place and report them."""

    def scan(source: str, line_base: int) -> str:
        out: list[str] = []
        position = 0
        while True:
            match = _COMMAND.search(source, position)
            if match is None:
                out.append(source[position:])
                return "".join(out)
            out.append(source[position : match.start()])
            name = match.group(1)
            line = line_base + source.count("\n", 0, match.start())
            arguments, end = _arguments(source, match.end())
            known = commands.get(name)
            if known is None or len(arguments) < known[0]:
                problems.append(BodyProblem("unknown_latex", "\\" + name, line))
                out.append(source[match.start() : end])  # left exactly as written
                position = end
                continue
            count, template = known
            if count == 0:
                # An empty {} after a symbol command is LaTeX's way of ending it; so is
                # the space after it, which LaTeX swallows.
                if arguments and arguments[0] == "":
                    position = _skip_group(source, match.end())
                elif source[match.end() : match.end() + 1] == " ":
                    position = match.end() + 1
                else:
                    position = match.end()
                out.append(template)
                continue
            used_end = match.end()
            for _ in range(count):
                used_end = _skip_group(source, used_end)
            out.append(template.format(*[scan(argument, line) for argument in arguments[:count]]))
            position = used_end

    return scan(text, 0)


def _arguments(source: str, position: int) -> tuple[list[str], int]:
    """The ``{...}`` groups that directly follow a command, and where they end."""
    found: list[str] = []
    while position < len(source) and source[position] == "{":
        end = _skip_group(source, position)
        if end == position:
            break
        found.append(source[position + 1 : end - 1])
        position = end
    return found, position


def _skip_group(source: str, position: int) -> int:
    """The index just past the ``{...}`` group starting at ``position`` (or ``position``)."""
    if position >= len(source) or source[position] != "{":
        return position
    depth = 0
    for index in range(position, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return position  # unbalanced: not a group
