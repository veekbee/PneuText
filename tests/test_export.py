from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pneutext.export import latex
from pneutext.store.library import Library
from tests.helpers import BOOK, GOLDEN
from tests.test_api_corpus import IMPORT
from tests.test_api_notes import create, span_of

COMMENTARY = {"folder": str(BOOK), "page_ref_commands": ["pref"]}
REPO = Path(__file__).resolve().parent.parent
BUILDER = shutil.which("latexmk") or shutil.which("tectonic")


@pytest.fixture
def version_id(client: TestClient) -> int:
    """The fixture book with its commentary, a few notes made in the app, all marked ready."""
    version = client.post("/api/imports/corpus", json={**IMPORT, "author": "A. N. Author"}).json()[
        "version_id"
    ]
    client.post(f"/api/versions/{version}/imports/commentary", json=COMMENTARY)
    types = {t["name"]: t["id"] for t in client.get("/api/note-types").json()}
    first = client.get(f"/api/versions/{version}/notes").json()
    brass = next(n["id"] for n in first if n["excerpt"].startswith("The instrument returns"))
    create(
        client,
        version,
        type_id=types["Comment"],
        span=span_of(client, version, "otters", 10),
        body_md=(
            f"Compare {{{{note:{brass}}}}} and {{{{fx:7.5-7.6}}}}; a {{{{gloss:camino|road}}}}.\n\n"
            "Costs 5% & more_or_less $2 #1 {braces} ~tilde^ <b>x</b> \\\\macro.\n\n"
            "TODO: never printed\n\n- one\n- *two*\n\n> quoted"
        ),
    )
    create(client, version, type_id=types["Comment"], span=span_of(client, version, "alder", 11))
    create(
        client,
        version,
        type_id=types["Comment"],
        span=span_of(client, version, "Three weeks", 11),
        body_md="A draft that is not published.",
    )
    notes = client.get(f"/api/versions/{version}/notes").json()
    ready = [n["id"] for n in notes if not n["excerpt"].startswith("A draft")]
    client.post(
        f"/api/versions/{version}/notes/status", json={"note_ids": ready, "status": "ready"}
    )
    return version


def profiles(client: TestClient) -> dict[str, int]:
    return {p["name"]: p["id"] for p in client.get("/api/export-profiles").json()}


def export(
    client: TestClient, version_id: int, folder: Path, edition: str = "Full edition"
) -> dict[str, Any]:
    response = client.post(
        f"/api/versions/{version_id}/exports/monograph",
        json={"profile_id": profiles(client)[edition], "folder": str(folder), "build_pdf": False},
    )
    assert response.status_code == 200, response.text
    return response.json()


def texts(folder: Path) -> dict[str, str]:
    return {
        str(path.relative_to(folder)): path.read_text("utf-8")
        for path in sorted(folder.rglob("*"))
        if path.suffix in (".tex", ".sty")
    }


def shingles(text: str, size: int = 5) -> set[tuple[str, ...]]:
    words = re.findall(r"[^\W\d_]+", text.lower())
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


# ---- Escaping -----------------------------------------------------------------------


def test_every_special_character_is_escaped() -> None:
    assert latex.escape(r"5% & $2 #1 a_b {x} ~ ^ \cmd <b> | \"") == (
        r"5\% \& \$2 \#1 a\_b \{x\} \textasciitilde{} \textasciicircum{} "
        r"\textbackslash{}cmd \textless{}b\textgreater{} \textbar{} \textbackslash{}\textquotedbl{}"
    )
    assert latex.escape("line\nbreak\x07 caf\u00e9 \U0001d11e") == "line break caf\u00e9 \U0001d11e"


def test_note_text_cannot_inject_latex(client: TestClient, version_id: int, tmp_path: Path) -> None:
    export(client, version_id, tmp_path)
    chapter = (tmp_path / "chapters" / "chapter-02.tex").read_text("utf-8")
    assert (
        r"Costs 5\% \& more\_or\_less \$2 \#1 \{braces\} \textasciitilde{}tilde\textasciicircum{} "
        r"\textless{}b\textgreater{}x\textless{}/b\textgreater{} \textbackslash{}macro."
    ) in chapter
    # No command of the note's own making reaches the source.
    assert "\\macro" not in chapter.replace(r"\textbackslash{}macro", "")


# ---- The project ----------------------------------------------------------------------


def test_the_export_is_a_latex_project(client: TestClient, version_id: int, tmp_path: Path) -> None:
    result = export(client, version_id, tmp_path)
    assert result["files"] == [
        "chapters/chapter-01.tex",
        "chapters/chapter-02.tex",
        "main.tex",
        "pneutext.sty",
        "figures/harbor.png",
    ]
    assert (result["notes"], result["pages"], result["pdf"]) == (13, 5, None)
    assert (tmp_path / "figures" / "harbor.png").read_bytes() == (BOOK / "harbor.png").read_bytes()
    assert result["warnings"] == ["The figure chain has no image; a placeholder is printed."]


def test_the_fixture_export_matches_its_golden_files(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path)
    actual = texts(tmp_path)
    golden = GOLDEN / "monograph"
    if os.environ.get("PNEUTEXT_UPDATE_GOLDEN") == "1":
        shutil.rmtree(golden, ignore_errors=True)
        for name, text in actual.items():
            (golden / name).parent.mkdir(parents=True, exist_ok=True)
            (golden / name).write_text(text, "utf-8")
    assert actual == texts(golden)


def test_output_is_deterministic(client: TestClient, version_id: int, tmp_path: Path) -> None:
    export(client, version_id, tmp_path / "one")
    export(client, version_id, tmp_path / "two")
    one = {
        p.relative_to(tmp_path / "one"): p.read_bytes()
        for p in (tmp_path / "one").rglob("*")
        if p.is_file()
    }
    two = {
        p.relative_to(tmp_path / "two"): p.read_bytes()
        for p in (tmp_path / "two").rglob("*")
        if p.is_file()
    }
    assert one == two and len(one) == 5


def test_each_chapter_opens_with_its_number_title_and_summary(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path)
    first = (tmp_path / "chapters" / "chapter-01.tex").read_text("utf-8")
    assert first.startswith(
        "\\pneuchapter{I}\n\\pneuchaptertitle{Arrival by Water}\n\\begin{pneuchaptersummary}\n"
        "Ada Quill reaches Low Harbor and learns that her employer is gone.\n"
        "\\end{pneuchaptersummary}\n"
    )
    second = (tmp_path / "chapters" / "chapter-02.tex").read_text("utf-8")
    assert second.startswith("\\pneuchapter{II}\n\n\\begin{pneupage}{10}")


def test_pages_with_notes_get_a_facsimile_then_their_notes_in_the_same_numbering(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path)
    first = (tmp_path / "chapters" / "chapter-01.tex").read_text("utf-8")
    assert re.findall(r"\\begin\{pneupage\}\{(\d+)\}", first) == ["7", "8", "9"]
    page_7 = first[first.index(r"\begin{pneupage}{7}") : first.index(r"\begin{pneupage}{8}")]
    # A marker for each highlight, numbered as the notes that follow.
    assert re.findall(r"\\pneumark\{[\d.]+\}\{[\d.]+\}\{(\d+)\}", page_7) == [
        "1",
        "2",
        "3",
        "4",
        "5",
    ]
    assert re.findall(r"\\pneunote\{(\d+)\}\{([^}]+)\}", page_7) == [
        ("1", "Historical"),
        ("2", "Comment"),
        ("3", "Definition"),
        ("4", "Literary"),
        ("5", "Meditation"),
    ]
    assert page_7.index(r"\end{pneupage}") < page_7.index(r"\begin{pneunotes}{7}")
    # Overlapping highlights are drawn as bands: two on line 9 of the print page.
    assert (
        page_7.count("\\pneuhl{12.000}{12.250}") == 1
        and page_7.count("\\pneuhl{12.250}{12.500}") == 1
    )
    # A page without exported notes has no facsimile.
    second = (tmp_path / "chapters" / "chapter-02.tex").read_text("utf-8")
    assert re.findall(r"\\begin\{pneupage\}\{(\d+)\}", second) == ["10", "12"]


def test_todo_remarks_drafts_and_empty_notes_never_appear(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path)
    everything = "\n".join(texts(tmp_path).values())
    for private in (
        "TODO",
        "never printed",
        "second pass",
        "check the make",
        "A draft that is not",
    ):
        assert private not in everything
    # The page note that held only a remark, and the bare highlights, are left out.
    assert "Imported span with no note" not in everything


def test_references_become_citations_linked_where_this_edition_has_the_target(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path)
    first = (tmp_path / "chapters" / "chapter-01.tex").read_text("utf-8")
    # Page 10 and page 12 both have facsimiles in this edition.
    assert r"see \pneupageref{10}{p.~10} and \pneupageref{12}{p.~12}." in first
    second = (tmp_path / "chapters" / "chapter-02.tex").read_text("utf-8")
    assert re.search(
        r"Compare \\pneunoteref\{\d+\}\{p\.~7, note~2\} and \\pneupageref\{7\}\{p\.~7\.5-7\.6\}",
        second,
    )
    assert r"a \pneugloss{camino}{road}." in second
    assert "\\begin{itemize}\n\\item one\n\\item \\emph{two}\n\\end{itemize}" in second
    assert "\\begin{quote}\nquoted\n\\end{quote}" in second


def test_a_first_reading_edition_leaves_out_level_two_and_degrades_references_to_it(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path, "First reading")
    main = (tmp_path / "main.tex").read_text("utf-8")
    assert "\\pneushowleveltrue" not in main
    first = (tmp_path / "chapters" / "chapter-01.tex").read_text("utf-8")
    assert "The instrument returns" not in first  # the level 2 note
    assert re.findall(r"\\pneunote\{(\d+)\}\{([^}]+)\}\{(\d)\}", first)[:2] == [
        ("1", "Historical", "1"),
        ("2", "Definition", "1"),
    ]
    # A reference to the excluded note is now a plain page citation.
    second = (tmp_path / "chapters" / "chapter-02.tex").read_text("utf-8")
    assert "Compare p.~7 and \\pneupageref{7}{p.~7.5-7.6}" in second
    assert "\\pneunoteref" not in second


def test_a_full_edition_marks_level_two_notes(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path)
    assert "\\pneushowleveltrue" in (tmp_path / "main.tex").read_text("utf-8")
    first = (tmp_path / "chapters" / "chapter-01.tex").read_text("utf-8")
    assert re.search(r"\\pneunote\{2\}\{Comment\}\{2\}\{\d+\}\nThe instrument returns", first)
    style = (tmp_path / "pneutext.sty").read_text("utf-8")
    assert r"\ifnum#3>1 \ifpneushowlevel\quad\pneuleveltwo\fi\fi" in style


def test_glossary_indexes_and_list_of_figures(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path)
    main = (tmp_path / "main.tex").read_text("utf-8")
    assert re.search(
        r"\\pneubackmatter\{Glossary\}\n\\pneuglossaryentry\{theodolite\}"
        r"\{a surveying instrument for measuring angles\}\{\\pneunoteref\{\d+\}\{p\.~7, note~3\}\}",
        main,
    )
    # One index per category, citing print pages; time has dates, not an index.
    assert re.findall(r"\\pneubackmatter\{Index of (\w+)\}", main) == [
        "places",
        "animals",
        "plants",
        "numbers",
        "weather",
    ]
    assert "\\pneuindexentry{forty-six (46)}{\\pneupageref{9}{9}}" in main
    assert "\\pneuindexentry{Low Harbor}{\\pneupageref{7}{7}}" in main
    assert "Index of time" not in main
    assert (
        "\\pneubackmatter{Figures}\n"
        "\\pneufigureentry{1}{The harbor at low water}{\\pneupageref{7}{7}}\n"
        "\\pneufigureentry{2}{A survey chain}{\\pneupageref{9}{9}}"
    ) in main
    first = (tmp_path / "chapters" / "chapter-01.tex").read_text("utf-8")
    assert r"\pneufigure{1}{figures/harbor.png}{The harbor at low water}{}" in first
    assert r"see \pneufigureref{1}." in first
    assert r"\pneufiguremissing{2}{A survey chain}{}" in first


def test_the_style_file_defines_every_command_the_export_uses(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path)
    files = texts(tmp_path)
    style = files.pop("pneutext.sty")
    defined = set(re.findall(r"\\newcommand\{\\(pneu\w+)\}", style))
    defined |= set(re.findall(r"\\newenvironment\{(pneu\w+)\}", style))
    defined |= {"pneushowleveltrue", "pneushowlevelfalse"}  # made by \newif
    used = set()
    for text in files.values():
        used |= set(re.findall(r"\\(pneu[a-z]+)", text))
        used |= set(re.findall(r"\\begin\{(pneu\w+)\}", text))
    used -= {name for name in used if name.startswith("pneutype")}  # colors, defined in main.tex
    assert used and used <= defined, f"not defined in the style file: {sorted(used - defined)}"


# ---- No corpus text ---------------------------------------------------------------------


def test_no_exported_file_contains_five_consecutive_words_of_the_corpus(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    """The leak test. Words the notes themselves contain are the author's, and allowed."""
    corpus = " ".join(
        line["text"]
        for page in range(7, 13)
        for line in client.get(f"/api/versions/{version_id}/pages/{page}/text").json()["lines"]
        if line["line_no"] is not None
    )
    notes = " ".join(
        client.get(f"/api/notes/{note['id']}").json()["body_md"]
        for note in client.get(f"/api/versions/{version_id}/notes").json()
    )
    forbidden = shingles(corpus) - shingles(notes)
    assert len(forbidden) > 500
    for edition in ("Full edition", "First reading"):
        folder = tmp_path / edition
        export(client, version_id, folder)
        for name, text in texts(folder).items():
            leaked = shingles(text) & forbidden
            assert not leaked, f"{name} contains corpus text: {sorted(leaked)[:3]}"


def test_the_leak_test_would_catch_a_line_of_the_book() -> None:
    line = "single heron stood in them, patient as a fence post. By"
    assert shingles(f"\\pneunote{{1}}{{Comment}}{{1}}{{9}}\n{line}") & shingles(line)


def test_the_export_package_cannot_reach_the_store() -> None:
    """The writers are given shapes and notes; they never import storage."""
    for path in sorted((REPO / "pneutext" / "export").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert not name.startswith(("pneutext.store", "pneutext.services", "sqlite3")), (
                    f"{path.name} imports {name}"
                )


# ---- Building ---------------------------------------------------------------------------


@pytest.mark.skipif(BUILDER is None, reason="neither latexmk nor tectonic is installed")
def test_the_fixture_export_compiles(client: TestClient, version_id: int, tmp_path: Path) -> None:
    export(client, version_id, tmp_path)
    assert BUILDER is not None
    command = (
        [BUILDER, "-lualatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
        if BUILDER.endswith("latexmk")
        else [BUILDER, "main.tex"]
    )
    done = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
    assert (tmp_path / "main.pdf").stat().st_size > 10_000


def test_without_latex_only_the_source_is_written(
    client: TestClient, version_id: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pneutext.services import export as export_service

    monkeypatch.setattr(export_service, "pdf_builder", lambda: None)
    response = client.post(
        f"/api/versions/{version_id}/exports/monograph",
        json={
            "profile_id": profiles(client)["Full edition"],
            "folder": str(tmp_path),
            "build_pdf": True,
        },
    )
    body = response.json()
    assert body["pdf"] is None
    assert body["build"] == "No LaTeX is installed, so only the source was written."
    assert (tmp_path / "main.tex").is_file()


def test_exporting_again_replaces_what_the_last_export_left(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    export(client, version_id, tmp_path)
    (tmp_path / "chapters" / "stale.tex").write_text("left over", "utf-8")
    (tmp_path / "my-notes.txt").write_text("the author's own file", "utf-8")
    export(client, version_id, tmp_path, "First reading")
    assert not (tmp_path / "chapters" / "stale.tex").exists()
    assert (tmp_path / "my-notes.txt").read_text("utf-8") == "the author's own file"


def test_the_default_folder_is_inside_the_library(
    client: TestClient, version_id: int, library: Library
) -> None:
    full = profiles(client)["Full edition"]
    defaults = client.get(
        f"/api/versions/{version_id}/exports/monograph/defaults", params={"profile_id": full}
    ).json()
    assert defaults["folder"] == str(library.root / "exports" / "fx-full-edition")
    result = client.post(
        f"/api/versions/{version_id}/exports/monograph",
        json={"profile_id": full, "build_pdf": False},
    ).json()
    assert result["folder"] == defaults["folder"]
    assert (library.root / "exports" / "fx-full-edition" / "main.tex").is_file()


# ---- Profiles ---------------------------------------------------------------------------


def test_two_editions_come_with_a_new_library_and_publish_only_ready_notes(
    client: TestClient,
) -> None:
    listed = client.get("/api/export-profiles").json()
    assert [(p["name"], p["type_ids"], p["levels"], p["statuses"]) for p in listed] == [
        ("First reading", None, [1], ["ready"]),
        ("Full edition", None, [1, 2], ["ready"]),
    ]


def test_profiles_are_saved_and_choose_types_levels_and_statuses(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    types = {t["name"]: t["id"] for t in client.get("/api/note-types").json()}
    created = client.post(
        "/api/export-profiles",
        json={
            "name": "Spanish and drafts",
            "type_ids": [types["Spanish"], types["Comment"]],
            "levels": [1, 2],
            "statuses": ["draft", "ready"],
        },
    )
    assert created.status_code == 201, created.text
    export(client, version_id, tmp_path, "Spanish and drafts")
    everything = "\n".join(texts(tmp_path).values())
    assert set(re.findall(r"\\pneunote\{\d+\}\{([^}]+)\}", everything)) == {"Spanish", "Comment"}
    assert "A draft that is not published." in everything

    profile = created.json()
    updated = client.put(
        f"/api/export-profiles/{profile['id']}",
        json={
            "name": "Spanish only",
            "type_ids": [types["Spanish"]],
            "levels": [1],
            "statuses": ["ready"],
        },
    ).json()
    assert (updated["name"], updated["type_ids"]) == ("Spanish only", [types["Spanish"]])
    assert client.delete(f"/api/export-profiles/{profile['id']}").status_code == 204
    assert "Spanish only" not in profiles(client)


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"name": "full edition"}, 409),
        ({"name": " "}, 400),
        ({"name": "x", "levels": []}, 400),
        ({"name": "x", "levels": [3]}, 400),
        ({"name": "x", "statuses": []}, 400),
        ({"name": "x", "type_ids": [999]}, 400),
        ({"name": "x", "type_ids": []}, 400),
    ],
)
def test_bad_profiles_are_explained(
    client: TestClient, body: dict[str, object], status: int
) -> None:
    assert client.post("/api/export-profiles", json=body).status_code == status


def test_missing_things_are_explained(client: TestClient, version_id: int, tmp_path: Path) -> None:
    missing = client.post(
        f"/api/versions/{version_id}/exports/monograph",
        json={"profile_id": 999, "folder": str(tmp_path)},
    )
    assert missing.status_code == 404
    a_file = tmp_path / "file.txt"
    a_file.write_text("x", "utf-8")
    full = profiles(client)["Full edition"]
    refused = client.post(
        f"/api/versions/{version_id}/exports/monograph",
        json={"profile_id": full, "folder": str(a_file)},
    )
    assert refused.status_code == 400


# ---- Backup -----------------------------------------------------------------------------


def backup(client: TestClient, folder: Path, include_text: bool) -> dict[str, Any]:
    response = client.post(
        "/api/exports/backup", json={"folder": str(folder), "include_text": include_text}
    )
    assert response.status_code == 200, response.text
    assert response.json()["files"] == ["library.json", "figures/harbor.png"]
    return json.loads((folder / "library.json").read_text("utf-8"))


def test_the_complete_backup_holds_the_whole_library(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    document = backup(client, tmp_path, include_text=True)
    assert (document["format"], document["includes_corpus_text"]) == ("pneutext-backup-1", True)
    tables = document["tables"]
    assert len(tables["segment"]) == 20 and len(tables["annotation"]) == 19
    assert tables["segment"][4]["text"].startswith("The ferry came into Low Harbor")
    assert any(row["exact"] == "otters" for row in tables["anchor"])
    assert {"work", "line", "mention", "entity", "figure", "link", "export_profile"} <= set(tables)
    assert (tmp_path / "figures" / "harbor.png").is_file()


def test_the_backup_without_text_keeps_offsets_only(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    document = backup(client, tmp_path, include_text=False)
    assert document["includes_corpus_text"] is False
    tables = document["tables"]
    assert all("text" not in row and row["length"] >= 0 for row in tables["segment"])
    assert tables["segment"][4]["length"] == 272
    assert all(row["exact"] == row["prefix"] == row["suffix"] == "" for row in tables["anchor"])
    assert all(row["start_offset"] >= 0 and row["end_offset"] >= 0 for row in tables["anchor"])
    # The notes are all there; the book is not.
    assert len(tables["annotation"]) == 19
    raw = (tmp_path / "library.json").read_text("utf-8")
    for page in range(7, 13):
        for line in client.get(f"/api/versions/{version_id}/pages/{page}/text").json()["lines"]:
            if line["line_no"] is not None and len(line["text"]) > 20:
                assert line["text"] not in raw
