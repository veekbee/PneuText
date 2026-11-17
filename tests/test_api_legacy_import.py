from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pneutext.store import db, entities, figures
from pneutext.store.library import Library
from tests.helpers import BOOK, assert_matches_golden
from tests.test_api_corpus import IMPORT, page_text
from tests.test_api_notes import create, page_notes, span_of, string_values

COMMENTARY = {"folder": str(BOOK), "page_ref_commands": ["pref"]}
PAGES = (7, 8, 9, 12)


@pytest.fixture
def version_id(client: TestClient) -> int:
    return client.post("/api/imports/corpus", json=IMPORT).json()["version_id"]


def preview(client: TestClient, version_id: int, **changes: object) -> dict[str, Any]:
    response = client.post(
        f"/api/versions/{version_id}/imports/commentary/preview", json={**COMMENTARY, **changes}
    )
    assert response.status_code == 200, response.text
    return response.json()


def commit(client: TestClient, version_id: int, **changes: object) -> dict[str, Any]:
    response = client.post(
        f"/api/versions/{version_id}/imports/commentary", json={**COMMENTARY, **changes}
    )
    assert response.status_code == 201, response.text
    return response.json()


def findings(report: dict[str, Any], group: str) -> list[tuple[str, int, int | None, str]]:
    items = next((g["items"] for g in report["groups"] if g["code"] == group), [])
    return [(i["code"], i["page"], i["line"], i["tag"]) for i in items]


def imported(client: TestClient, version_id: int, types: dict[int, str]) -> list[dict[str, Any]]:
    """Every imported note, with the words its span covers (read from the text projection)."""
    out = []
    seen: set[int] = set()
    for page in range(7, 13):
        lines = page_text(client, version_id, page)["lines"]
        for note in page_notes(client, version_id, page):
            if note["id"] in seen:
                continue
            seen.add(note["id"])
            words = [
                line["text"][mark["start"] : mark["end"]]
                for line in lines
                for mark in line["highlights"]
                if mark["annotation_id"] == note["id"]
            ]
            out.append(
                {
                    "page": page,
                    "legacy_id": note["legacy_id"],
                    "type": types[note["type_id"]],
                    "scope": note["scope"],
                    "level": note["level"],
                    "status": note["status"],
                    "body_md": note["body_md"],
                    "span_on_this_page": words,
                }
            )
    return out


def mentions(library: Library, version_id: int) -> list[dict[str, Any]]:
    with db.transaction(library.db_path) as conn:
        rows = entities.list_mentions(conn, version_id)
        texts = {r["id"]: r["text"] for r in conn.execute("SELECT id, text FROM segment")}
    return [
        {
            "category": row.category,
            "entity": row.entity,
            "value": row.value,
            "words": texts[row.start_segment_id][row.start_offset : row.end_offset],
        }
        for row in rows
    ]


def test_the_dry_run_reports_every_problem_grouped_and_writes_nothing(
    client: TestClient, version_id: int, library: Library
) -> None:
    report = preview(client, version_id)
    summary = {k: v for k, v in report.items() if k not in ("groups", "repairs")}
    assert summary == {
        "files": 5,
        "pages": [7, 8, 9, 12],
        "notes": 13,
        "flagged_notes": 3,
        "chapter_notes": 2,
        "remarks": 1,
        "mentions": 16,
        "new_categories": ["weather"],
        "new_types": [],
        "figures": 2,
        "replaced_notes": 0,
        "replaced_mentions": 0,
    }
    assert [g["code"] for g in report["groups"]] == [
        "malformed_tags",
        "span_without_note",
        "note_without_span",
        "type_disagreement",
        "wrong_page",
        "unknown_category",
        "missing_figure",
        "text_differs",
        "unknown_latex",
    ]
    assert findings(report, "malformed_tags") == [
        ("stray_closing_tag", 9, 1, "{c_p9_none/}"),
        ("malformed_tag", 9, 2, "{c_p9_ahead"),
        ("unclosed_span", 9, 11, "{m_p9_white}"),
        ("unclosed_block", 9, 26, "{m_p9_white}"),
    ]
    assert findings(report, "span_without_note") == [("span_without_note", 8, 13, "{c_p8_marsh}")]
    assert findings(report, "note_without_span") == [("note_without_span", 8, 26, "{c_p8_barrow}")]
    assert findings(report, "type_disagreement") == [
        ("type_mismatch", 9, 16, "{s_p9_cuidado}"),
        ("bad_level", 9, 20, "{c_p7_sheet}"),
    ]
    assert findings(report, "wrong_page") == [("wrong_page", 9, 20, "{c_p7_sheet}")]
    assert findings(report, "unknown_category") == [("unknown_category", 9, 7, "|weather|")]
    assert findings(report, "missing_figure") == [("missing_figure", 9, 23, "chain.png")]
    assert findings(report, "text_differs") == [
        ("text_differs", 9, 2, "corpus line 2"),
        ("text_differs", 9, 12, "corpus line 11"),
        ("page_not_in_corpus", 99, None, "FX_comm_p099.txt"),
    ]
    assert findings(report, "unknown_latex") == [("unknown_latex", 9, 21, "\\sidenote")]
    # Only the unambiguous is repaired, and each repair is listed.
    assert [(r["code"], r["page"], r["line"], r["tag"]) for r in report["repairs"]] == [
        ("closing_tag_slash", 8, 10, "{h_p8_candle}"),
        ("category_name", 8, 3, "|animal|"),
        ("category_name", 8, 8, "|times|"),
    ]

    # Nothing was written.
    for page in range(7, 13):
        assert page_notes(client, version_id, page) == []
    with db.transaction(library.db_path) as conn:
        assert entities.list_mentions(conn, version_id) == []
        assert figures.list_figures(conn) == []
        assert [c.name for c in entities.list_categories(conn)] == [
            "places",
            "animals",
            "plants",
            "numbers",
            "time",
        ]
    assert list(library.figures_dir.iterdir()) == []


def shingles(text: str, size: int = 3) -> set[tuple[str, ...]]:
    """Every run of ``size`` consecutive words in a text, lower-cased."""
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


def test_the_report_quotes_tags_and_places_never_the_text(
    client: TestClient, version_id: int
) -> None:
    report = preview(client, version_id)
    said = " ".join(string_values(report))
    book = " ".join(
        line["text"]
        for number in range(7, 13)
        for line in page_text(client, version_id, number)["lines"]
        if line["line_no"] is not None
    )
    # No run of three words from the book appears anywhere in the report.
    assert not shingles(said) & shingles(book)
    # Nor do the private words of the notes and remarks themselves.
    for private in ("second pass", "barrow comes back", "three sheets", "private", "Tide tables"):
        assert private not in said
    # What it does carry is the tag, the page and the line.
    assert "{c_p8_marsh}" in said and "Page 8, line 13" in said


def test_importing_gives_the_same_report_and_matches_the_golden_notes(
    client: TestClient, version_id: int, library: Library
) -> None:
    dry = preview(client, version_id)
    report = commit(client, version_id)
    assert report == dry

    types = {t["id"]: t["name"] for t in client.get("/api/note-types").json()}
    notes = imported(client, version_id, types)
    assert len(notes) == 16
    assert {note["status"] for note in notes} == {"draft"}
    assert_matches_golden(
        "book_commentary.json",
        {"report": report, "notes": notes, "mentions": mentions(library, version_id)},
    )


def test_spans_land_on_the_words_they_enclosed(client: TestClient, version_id: int) -> None:
    commit(client, version_id)
    types = {t["id"]: t["name"] for t in client.get("/api/note-types").json()}
    by_id = {n["legacy_id"]: n for n in imported(client, version_id, types) if n["legacy_id"]}
    assert by_id["h_p7_tide"]["span_on_this_page"] == ["last tide of", "October, 1871"]
    assert by_id["c_p7_brass"]["span_on_this_page"] == ["brass", "theodolite in one hand"]
    assert by_id["cl_p7_theo"]["span_on_this_page"] == ["theodolite"]
    assert by_id["l_p7_tin"]["span_on_this_page"] == ["kept his ledgers in a biscuit tin"]
    assert by_id["m_p7_biscuit"]["span_on_this_page"] == ["biscuit tin. He told her"]
    assert by_id["h_p8_candle"]["span_on_this_page"] == ["Candlemas"]
    assert by_id["c_p8_marsh"]["span_on_this_page"] == ["marsh turned out to", "contain."]
    # After a character outside the BMP, offsets still count code points.
    assert by_id["c_p12_sign"]["span_on_this_page"] == ["beside it"]
    # A span that was never closed runs to the end of its line.
    assert by_id["m_p9_white"]["span_on_this_page"] == ["white part"]


def test_types_levels_and_flags_follow_the_rules(client: TestClient, version_id: int) -> None:
    commit(client, version_id)
    types = {t["id"]: t["name"] for t in client.get("/api/note-types").json()}
    notes = imported(client, version_id, types)
    by_id = {n["legacy_id"]: n for n in notes if n["legacy_id"]}
    # The block header names the type; without one, the id's prefix does.
    assert by_id["h_p7_tide"]["type"] == "Historical"
    assert by_id["s_p9_cuidado"]["type"] == "Historical"  # header wins over the prefix
    assert by_id["c_p8_marsh"]["type"] == "Comment"  # from the prefix alone
    # A body that is one definition becomes a Definition.
    assert by_id["cl_p7_theo"]["type"] == "Definition"
    assert (by_id["c_p7_brass"]["level"], by_id["h_p7_tide"]["level"]) == (2, 1)
    assert by_id["c_p7_sheet"]["level"] == 1  # 5 is not a level

    # Flags are TODO remarks at the head of the note.
    assert by_id["c_p8_barrow"]["scope"] == "page"
    assert by_id["c_p8_barrow"]["body_md"].startswith("TODO: Imported without a span.")
    assert by_id["c_p8_barrow"]["body_md"].endswith("The barrow comes back in the second chapter.")
    assert by_id["c_p8_marsh"]["body_md"].startswith("TODO: Imported span with no note.")
    assert by_id["m_p9_white"]["body_md"].startswith("TODO: Imported from a span that was never")
    assert "What the map leaves out." in by_id["m_p9_white"]["body_md"]

    # Chapter matter and remarks outside any block.
    chapter = [n for n in notes if n["scope"] == "chapter"]
    assert [(n["type"], n["body_md"]) for n in chapter] == [
        ("Chapter title", "Arrival by Water"),
        ("Chapter summary", "Ada Quill reaches Low Harbor and learns that her employer is gone."),
    ]
    remarks = [n for n in notes if n["legacy_id"] is None and n["scope"] == "page"]
    assert [(n["page"], n["body_md"]) for n in remarks] == [
        (7, "TODO: whole page needs a second pass")
    ]


def test_bodies_are_converted(client: TestClient, version_id: int) -> None:
    commit(client, version_id)
    types = {t["id"]: t["name"] for t in client.get("/api/note-types").json()}
    by_id = {n["legacy_id"]: n for n in imported(client, version_id, types) if n["legacy_id"]}
    assert by_id["h_p7_tide"]["body_md"] == (
        "Tide tables for the period survive; see {{fx:10}} and {{fx:12}}."
    )
    assert by_id["c_p7_brass"]["body_md"] == (
        "The instrument returns at the end. **Watch** the brass.\n\n"
        "TODO: check the make of the theodolite"
    )
    assert by_id["l_p7_tin"]["body_md"] == (
        "![The harbor at low water](fig:harbor)\n\n"
        "The tin is the first container in the story; see {{fig:harbor}}."
    )
    assert by_id["m_p7_biscuit"]["body_md"] == (
        "Debt as inheritance\u2014a theme.\n\nTODO: compare the second sheet"
    )
    assert by_id["s_p8_senora"]["body_md"] == "{{gloss:se\u00f1ora|madam, lady}}"
    # An unknown command stays exactly as written.
    assert "\\sidenote{check}" in by_id["c_p7_sheet"]["body_md"]


def test_a_page_reference_command_is_only_known_when_configured(
    client: TestClient, version_id: int
) -> None:
    report = preview(client, version_id, page_ref_commands=[])
    assert ("unknown_latex", 7, 25, "\\pref") in findings(report, "unknown_latex")


def test_entity_mentions_are_indexed_by_category(
    client: TestClient, version_id: int, library: Library
) -> None:
    commit(client, version_id)
    found = mentions(library, version_id)
    assert [(m["category"], m["entity"], m["value"], m["words"]) for m in found] == [
        ("places", "Low Harbor", None, "Low Harbor"),
        ("numbers", "nine", "9", "nine"),
        ("places", "Low Harbor", None, "Low Harbor"),
        ("time", None, None, "October, 1871"),
        ("animals", "gulls", None, "gulls"),
        ("numbers", "nine", "9", "nine"),
        ("plants", "Reeds", None, "Reeds"),
        ("animals", "heron", None, "heron"),  # tagged |animal|, repaired
        ("time", None, None, "third day"),  # tagged |times|, repaired
        ("numbers", "eleven", "11", "eleven"),
        ("animals", "eels", None, "eels"),
        ("numbers", "two", "2", "two"),
        ("plants", "willow", None, "willow"),
        ("numbers", "forty-six", "46", "forty-six"),
        ("weather", "sea", None, "sea"),  # an unknown category is created, not dropped
        ("numbers", "forty-seven", "47", "forty-seven"),
    ]
    with db.transaction(library.db_path) as conn:
        assert [c.name for c in entities.list_categories(conn)][-1] == "weather"
        # Two mentions of one place share an entity.
        assert (
            conn.execute("SELECT COUNT(*) FROM entity WHERE name = 'Low Harbor'").fetchone()[0] == 1
        )


def test_figures_are_copied_into_the_library(
    client: TestClient, version_id: int, library: Library
) -> None:
    commit(client, version_id)
    with db.transaction(library.db_path) as conn:
        rows = figures.list_figures(conn)
    assert [(f.label, f.file, f.caption) for f in rows] == [
        ("chain", "chain.png", "A survey chain"),  # its file is missing, and reported
        ("harbor", "harbor.png", "The harbor at low water"),
    ]
    assert [p.name for p in library.figures_dir.iterdir()] == ["harbor.png"]
    assert (library.figures_dir / "harbor.png").read_bytes() == (BOOK / "harbor.png").read_bytes()


def test_figures_can_come_from_a_folder_of_their_own(
    client: TestClient, version_id: int, library: Library, tmp_path: Path
) -> None:
    shutil.copyfile(BOOK / "harbor.png", tmp_path / "chain.png")
    report = commit(client, version_id, figures_folder=str(tmp_path))
    assert findings(report, "missing_figure") == []
    assert sorted(p.name for p in library.figures_dir.iterdir()) == ["chain.png", "harbor.png"]


def test_importing_again_replaces_what_came_from_the_files_and_nothing_else(
    client: TestClient, version_id: int, library: Library
) -> None:
    first = commit(client, version_id)
    types = {t["id"]: t["name"] for t in client.get("/api/note-types").json()}
    before = imported(client, version_id, types)
    before_mentions = mentions(library, version_id)

    # A note made in the app, on a page that has commentary, and an edit to an imported note.
    type_ids = {name: type_id for type_id, name in types.items()}
    own = create(
        client,
        version_id,
        type_id=type_ids["Comment"],
        span=span_of(client, version_id, "single heron", 8),
        body_md="Made in the app.",
    )
    edited = next(n for n in page_notes(client, version_id, 8) if n["legacy_id"] == "h_p8_candle")
    client.patch(f"/api/notes/{edited['id']}", json={"body_md": "Edited in the app."})

    again = commit(client, version_id)
    assert (again["replaced_notes"], again["replaced_mentions"]) == (16, 16)
    # The category the first import created is now known, so it is no longer reported.
    assert again["new_categories"] == []
    assert findings(again, "unknown_category") == []
    changed = ("replaced_notes", "replaced_mentions", "new_categories", "groups")
    assert {k: v for k, v in again.items() if k not in changed} == {
        k: v for k, v in first.items() if k not in changed
    }
    assert [g for g in again["groups"]] == [
        g for g in first["groups"] if g["code"] != "unknown_category"
    ]

    after = imported(client, version_id, types)
    assert [n for n in after if n["body_md"] != "Made in the app."] == before
    assert mentions(library, version_id) == before_mentions
    # The app's own note is untouched; the imported note is back to what the file says.
    assert client.get(f"/api/notes/{own['id']}").json()["body_md"] == "Made in the app."
    assert client.get(f"/api/notes/{edited['id']}").status_code == 404
    with db.transaction(library.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM entity_category").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM figure").fetchone()[0] == 2
        # 16 notes, 16 mentions, the app's note, and the two passages one note refers
        # to. Importing twice has left no anchor behind.
        total = conn.execute("SELECT COUNT(*) FROM anchor").fetchone()[0]
        assert total == 16 + 16 + 1 + 2


def test_the_dry_run_says_what_a_second_import_would_replace(
    client: TestClient, version_id: int
) -> None:
    commit(client, version_id)
    report = preview(client, version_id)
    assert (report["replaced_notes"], report["replaced_mentions"]) == (16, 16)


def test_a_failed_import_leaves_nothing_behind(
    client: TestClient, version_id: int, library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_: object) -> int:
        raise RuntimeError("simulated failure part-way through")

    monkeypatch.setattr(entities, "insert_mention", explode)
    with pytest.raises(RuntimeError):
        client.post(f"/api/versions/{version_id}/imports/commentary", json=COMMENTARY)
    for page in range(7, 13):
        assert page_notes(client, version_id, page) == []
    with db.transaction(library.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM anchor").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM entity_category").fetchone()[0] == 5


@pytest.mark.parametrize(
    ("change", "status", "expected"),
    [
        ({"folder": "/no/such/folder"}, 400, "no folder"),
        ({"folder": " "}, 400, "Give the folder"),
        ({"file_pattern": "_nothing_p(?P<page>\\d+)"}, 400, "No page files"),
    ],
)
def test_bad_requests_are_explained(
    client: TestClient, version_id: int, change: dict[str, str], status: int, expected: str
) -> None:
    response = client.post(
        f"/api/versions/{version_id}/imports/commentary/preview", json={**COMMENTARY, **change}
    )
    assert response.status_code == status
    assert expected in response.json()["detail"]


def test_an_unknown_version_is_explained(client: TestClient) -> None:
    response = client.post("/api/versions/999/imports/commentary/preview", json=COMMENTARY)
    assert response.status_code == 404


def test_a_type_the_files_name_but_the_library_lacks_is_created(
    client: TestClient, version_id: int, tmp_path: Path
) -> None:
    """Imported as found: the notes keep the type their block names."""
    text = (BOOK / "FX_corp_p012.txt").read_text("utf-8")
    marked = text.replace("heron,", "{t_p12_bird}heron{t_p12_bird/},").replace(
        "a step.", "{q_p12_step}a step{q_p12_step/}.{x_p12_none}x{x_p12_none/}"
    )
    assert marked != text
    (tmp_path / "FX_comm_p012.txt").write_text(
        marked.replace("{x_p12_none}x{x_p12_none/}", "")
        + "\n@@ Metatext\n\n{t_p12_bird}, type=Theme, read=2\n"
        "Birds as witnesses.\n{t_p12_bird/}\n\n"
        "{q_p12_step}, Question\nWhose step?\n{q_p12_step/}\n",
        "utf-8",
    )
    report = commit(client, version_id, folder=str(tmp_path))
    assert report["new_types"] == ["Theme", "Question"]
    assert [(c, p, t) for c, p, _, t in findings(report, "type_disagreement")] == [
        ("new_note_type", 12, "{t_p12_bird}"),
        ("new_note_type", 12, "{q_p12_step}"),
    ]
    listed = {t["name"]: t for t in client.get("/api/note-types").json()}
    # Each new type takes the id's prefix as its code, since that code was free.
    assert (listed["Theme"]["code"], listed["Question"]["code"]) == ("t", "q")
    notes = {n["legacy_id"]: n for n in page_notes(client, version_id, 12)}
    assert notes["t_p12_bird"]["type_id"] == listed["Theme"]["id"]
    assert notes["t_p12_bird"]["level"] == 2  # read=2, the older way of writing the level
    assert notes["q_p12_step"]["type_id"] == listed["Question"]["id"]
    # Importing again finds the types already there.
    again = commit(client, version_id, folder=str(tmp_path))
    assert again["new_types"] == [] and findings(again, "type_disagreement") == []
    assert len(client.get("/api/note-types").json()) == len(listed)
