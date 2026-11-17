from __future__ import annotations

import pytest

from pneutext.importers.legacy_body import BodyFormat, FigureUse, convert, figure_label

FMT = BodyFormat(work_code="fx", page_ref_commands=("pref",))


def md(body: str, fmt: BodyFormat = FMT) -> str:
    return convert(body, fmt).markdown


def test_page_references_in_the_target_syntax_are_left_alone() -> None:
    assert md("See {{fx:292-293}} and {{fx:45.12}}.") == "See {{fx:292-293}} and {{fx:45.12}}."


def test_a_configured_page_reference_command_becomes_a_reference_to_the_work() -> None:
    assert md(r"See \pref{108} and \pref{12-14}.") == "See {{fx:108}} and {{fx:12-14}}."


def test_page_reference_commands_are_configuration_not_code() -> None:
    result = convert(r"See \pref{108}.", BodyFormat(work_code="fx"))
    assert result.markdown == r"See \pref{108}."
    assert [(p.code, p.tag) for p in result.problems] == [("unknown_latex", r"\pref")]


def test_gloss_and_figure_reference_commands() -> None:
    assert md(r"\spanish{camino}{road, way}") == "{{gloss:camino|road, way}}"
    assert md(r"As \reffig{harbor} shows.") == "As {{fig:harbor}} shows."


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        (r"\textbf{Watch} it.", "**Watch** it."),
        (r"\textit{soft} and \emph{softer}", "*soft* and *softer*"),
        (r"a \textbf{bold \emph{nested}} b", "a **bold *nested*** b"),
        (r"debt\textemdash a theme", "debt\u2014a theme"),
        (r"debt\textemdash{}a theme", "debt\u2014a theme"),
        (r"1871\textendash 1872", "1871\u20131872"),
        (r"and so\ldots", "and so\u2026"),
        ("``quoted''", "\u201cquoted\u201d"),
        (r"50\% of it", r"50\% of it"),
    ],
)
def test_known_latex_becomes_markdown(legacy: str, expected: str) -> None:
    result = convert(legacy, FMT)
    assert result.markdown == expected
    assert result.problems == []


def test_an_unknown_command_is_left_in_place_and_reported_by_name_and_line() -> None:
    result = convert("First line.\n\nThen \\sidenote{private words} here.", FMT)
    assert result.markdown == "First line.\n\nThen \\sidenote{private words} here."
    (problem,) = result.problems
    assert (problem.code, problem.tag, problem.line) == ("unknown_latex", r"\sidenote", 2)


def test_a_known_command_missing_its_argument_is_reported_not_guessed() -> None:
    result = convert(r"\textbf without braces", FMT)
    assert result.markdown == r"\textbf without braces"
    assert [p.tag for p in result.problems] == [r"\textbf"]


def test_both_legacy_figure_forms_become_a_placed_figure() -> None:
    result = convert(
        "(The harbor at low water)[harbor.jpg]\n\nText.\n\n[A chain](Survey Chain.PNG)", FMT
    )
    assert result.markdown == (
        "![The harbor at low water](fig:harbor)\n\nText.\n\n![A chain](fig:survey-chain)"
    )
    assert result.figures == [
        FigureUse("harbor", "harbor.jpg", "The harbor at low water", 0),
        FigureUse("survey-chain", "Survey Chain.PNG", "A chain", 4),
    ]


def test_web_links_and_ordinary_links_are_not_figures() -> None:
    body = "[site](https://example.test/a.png) and [notes](other.txt) and (aside)[not a file]"
    result = convert(body, FMT)
    assert result.markdown == body
    assert result.figures == []


def test_figure_labels_come_from_file_names() -> None:
    assert figure_label("harbor.png") == "harbor"
    assert figure_label("plates/Low Harbor (2).JPG") == "low-harbor-2"
    assert figure_label(".png") == "figure"


def test_an_xxx_paragraph_becomes_a_todo_paragraph() -> None:
    assert md("A note.\n\nXXX check the date\nand the place\n\nMore.") == (
        "A note.\n\nTODO: check the date\nand the place\n\nMore."
    )
    assert md("XXX: fix") == "TODO: fix"


def test_a_line_starting_xxx_is_always_a_remark_even_straight_after_text() -> None:
    # A private remark must never be taken for part of the note and published.
    assert md("The mark is here.\nXXX check this\nand that\n\nMore.") == (
        "The mark is here.\n\nTODO: check this\nand that\n\nMore."
    )
    # Remarks on consecutive lines are separate remarks.
    assert md("XXX (first)\nXXX (second)") == "TODO: (first)\n\nTODO: (second)"


def test_xxx_within_a_line_or_a_longer_word_is_not_a_remark() -> None:
    assert md("The mark XXX is drawn here.") == "The mark XXX is drawn here."
    assert md("XXXL sizes") == "XXXL sizes"


def test_a_comment_line_becomes_a_todo_paragraph_of_its_own() -> None:
    assert md("Debt is a theme.\n% compare the second sheet\nIt returns.") == (
        "Debt is a theme.\n\nTODO: compare the second sheet\n\nIt returns."
    )


def test_a_definition_is_recognized_only_as_a_whole_body() -> None:
    assert convert("**theodolite** - a surveying instrument", FMT).is_definition is True
    assert convert("**theodolite** - an instrument\n\nAnd more.", FMT).is_definition is True
    assert convert("See **theodolite** - an instrument", FMT).is_definition is False
    assert convert("**theodolite** is an instrument", FMT).is_definition is False


def test_an_empty_body_stays_empty() -> None:
    result = convert("\n\n", FMT)
    assert (result.markdown, result.figures, result.problems) == ("", [], [])


def test_the_older_citation_form_and_a_capitalized_gloss_command() -> None:
    assert md("As {{bib:smith1999, pp. 12-14}} says.") == "As {{cite:smith1999, pp. 12-14}} says."
    result = convert(r"\Spanish{camino}{road}", FMT)
    assert (result.markdown, result.problems) == ("{{gloss:camino|road}}", [])
