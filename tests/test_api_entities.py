from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.helpers import BOOK
from tests.test_api_corpus import IMPORT, page_text
from tests.test_api_notes import create, span_of, string_values
from tests.test_api_shape import corpus_words, page_shape

COMMENTARY = {"folder": str(BOOK), "page_ref_commands": ["pref"]}


@pytest.fixture
def version_id(client: TestClient) -> int:
    return client.post("/api/imports/corpus", json=IMPORT).json()["version_id"]


@pytest.fixture
def categories(client: TestClient) -> dict[str, int]:
    return {c["name"]: c["id"] for c in client.get("/api/entity-categories").json()}


def tag(client: TestClient, version_id: int, phrase: str, page: int, **fields: object) -> int:
    body = {"span": span_of(client, version_id, phrase, page), **fields}
    response = client.post(f"/api/versions/{version_id}/mentions", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def index(client: TestClient, version_id: int, **params: object) -> list[dict[str, Any]]:
    response = client.get(f"/api/versions/{version_id}/entities", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def chronology(client: TestClient, version_id: int) -> list[dict[str, Any]]:
    response = client.get(f"/api/versions/{version_id}/chronology")
    assert response.status_code == 200, response.text
    return response.json()


def set_time(client: TestClient, mention_id: int, **value: object) -> None:
    response = client.put(f"/api/mentions/{mention_id}/time", json=value)
    assert response.status_code == 204, response.text


# ---- Categories -------------------------------------------------------------------


def test_a_new_library_has_five_categories_and_time_is_one(client: TestClient) -> None:
    listed = client.get("/api/entity-categories").json()
    assert [(c["name"], c["is_time"]) for c in listed] == [
        ("places", False),
        ("animals", False),
        ("plants", False),
        ("numbers", False),
        ("time", True),
    ]


def test_the_author_can_add_rename_and_recolor_categories(client: TestClient) -> None:
    created = client.post("/api/entity-categories", json={"name": "  weather  "})
    assert created.status_code == 201
    weather = created.json()
    assert (weather["name"], weather["is_time"]) == ("weather", False)
    renamed = client.patch(
        f"/api/entity-categories/{weather['id']}", json={"name": "skies", "color": "#336699"}
    ).json()
    assert (renamed["name"], renamed["color"]) == ("skies", "#336699")
    assert [c["name"] for c in client.get("/api/entity-categories").json()][-1] == "skies"

    assert client.post("/api/entity-categories", json={"name": "Places"}).status_code == 409
    assert client.post("/api/entity-categories", json={"name": " "}).status_code == 400
    bad = client.patch(f"/api/entity-categories/{weather['id']}", json={"color": "blue"})
    assert bad.status_code == 400
    assert client.patch("/api/entity-categories/999", json={"name": "x"}).status_code == 404


def test_merging_categories_moves_entities_and_joins_namesakes(
    client: TestClient, version_id: int, categories: dict[str, int]
) -> None:
    birds = client.post("/api/entity-categories", json={"name": "birds"}).json()["id"]
    tag(client, version_id, "heron", 8, category_id=birds)
    tag(client, version_id, "gulls", 7, category_id=birds)
    tag(client, version_id, "heron", 12, category_id=categories["animals"], entity_name="Heron")

    merged = client.post(
        f"/api/entity-categories/{birds}/merge", json={"into_id": categories["animals"]}
    )
    assert merged.status_code == 204
    assert "birds" not in [c["name"] for c in client.get("/api/entity-categories").json()]
    animals = index(client, version_id, category_id=categories["animals"])
    assert [(e["name"], [p["page"] for p in e["places"]]) for e in animals] == [
        ("gulls", [7]),
        ("Heron", [8, 12]),  # the two herons are now one entry
    ]
    time = client.post(
        f"/api/entity-categories/{categories['time']}/merge", json={"into_id": categories["places"]}
    )
    assert time.status_code == 400


# ---- Tagging and the index --------------------------------------------------------


def test_tagging_a_selection_adds_its_page_to_the_entity(
    client: TestClient, version_id: int, categories: dict[str, int]
) -> None:
    tag(client, version_id, "Low Harbor", 7, category_id=categories["places"])
    (entry,) = index(client, version_id, category_id=categories["places"])
    assert (entry["name"], entry["value"]) == ("Low Harbor", None)  # named by the words tagged
    assert entry["places"] == [{"page": 7, "line_no": 1}]  # its first occurrence, in the synopsis

    # Tagging another occurrence, by entity id, adds that page to the same entry.
    tag(client, version_id, "Low", 9, category_id=categories["places"], entity_id=entry["id"])
    (entry,) = index(client, version_id, category_id=categories["places"])
    assert [p["page"] for p in entry["places"]] == [7, 9]


def test_an_entity_can_be_chosen_by_name_with_type_ahead_or_made_new(
    client: TestClient, version_id: int, categories: dict[str, int]
) -> None:
    places = categories["places"]
    tag(client, version_id, "Low Harbor", 7, category_id=places)
    tag(client, version_id, "Saint Bride", 11, category_id=places, entity_name="Saint Bride's Acre")
    starting = index(client, version_id, category_id=places, starting="sa")
    assert [e["name"] for e in starting] == ["Saint Bride's Acre"]
    assert [e["name"] for e in index(client, version_id, category_id=places, starting="l")] == [
        "Low Harbor"
    ]
    # The same name again (in any case) is the same entity.
    tag(client, version_id, "marsh", 8, category_id=places, entity_name="low harbor")
    assert [e["name"] for e in index(client, version_id, category_id=places)] == [
        "Low Harbor",
        "Saint Bride's Acre",
    ]


def test_entities_carry_a_normalized_value_and_are_found_by_it(
    client: TestClient, version_id: int, categories: dict[str, int]
) -> None:
    numbers = categories["numbers"]
    tag(client, version_id, "forty-six", 9, category_id=numbers, value="46")
    tag(client, version_id, "nine", 7, category_id=numbers, value="9")
    tag(
        client,
        version_id,
        "stations",
        9,
        category_id=numbers,
        entity_name="46 stations",
        value="46",
    )
    listed = index(client, version_id, category_id=numbers)
    assert [(e["name"], e["value"], len(e["places"])) for e in listed] == [
        ("forty-six", "46", 2),
        ("nine", "9", 1),
    ]


def test_entities_are_renamed_given_values_and_merged(
    client: TestClient, version_id: int, categories: dict[str, int]
) -> None:
    animals = categories["animals"]
    tag(client, version_id, "heron", 8, category_id=animals)
    tag(client, version_id, "heron", 12, category_id=animals, entity_name="grey heron")
    tag(client, version_id, "gulls", 7, category_id=animals)
    by_name = {e["name"]: e for e in index(client, version_id, category_id=animals)}

    renamed = client.patch(
        f"/api/entities/{by_name['heron']['id']}", json={"name": "Heron", "value": "Ardea"}
    )
    assert renamed.status_code == 204
    clash = client.patch(f"/api/entities/{by_name['gulls']['id']}", json={"name": "Heron"})
    assert clash.status_code == 409
    assert "Merge" in clash.json()["detail"]

    merged = client.post(
        f"/api/entities/{by_name['grey heron']['id']}/merge",
        json={"into_id": by_name["heron"]["id"]},
    )
    assert merged.status_code == 204
    after = index(client, version_id, category_id=animals)
    assert [(e["name"], e["value"], [p["page"] for p in e["places"]]) for e in after] == [
        ("gulls", None, [7]),
        ("Heron", "Ardea", [8, 12]),
    ]
    # A value can be cleared again.
    client.patch(f"/api/entities/{by_name['heron']['id']}", json={"value": ""})
    assert index(client, version_id, category_id=animals)[1]["value"] is None

    other = tag(client, version_id, "Low Harbor", 7, category_id=categories["places"])
    assert other
    place = index(client, version_id, category_id=categories["places"])[0]
    across = client.post(
        f"/api/entities/{place['id']}/merge", json={"into_id": by_name["heron"]["id"]}
    )
    assert across.status_code == 400


def test_mentions_are_marked_on_the_page_in_both_projections_without_text(
    client: TestClient, version_id: int, categories: dict[str, int]
) -> None:
    first = tag(client, version_id, "single heron", 8, category_id=categories["animals"])
    second = tag(client, version_id, "window faced", 8, category_id=categories["places"])
    text = page_text(client, version_id, 8)
    marked = {
        line["line_no"]: [
            (m["mention_id"], line["text"][m["start"] : m["end"]]) for m in line["mentions"]
        ]
        for line in text["lines"]
        if line["mentions"]
    }
    # The second mention crosses a print line; the joining space is not marked.
    assert marked == {1: [(second, "window")], 2: [(second, "faced")], 3: [(first, "single heron")]}
    shape = page_shape(client, version_id, 8)
    for shape_line, text_line in zip(shape["lines"], text["lines"], strict=True):
        assert shape_line["mentions"] == text_line["mentions"]
    assert {m["category_id"] for line in shape["lines"] for m in line["mentions"]} == {
        categories["animals"],
        categories["places"],
    }
    words = set(re.findall(r"[a-z]{4,}", " ".join(string_values(shape)).lower())) & corpus_words()
    assert words <= {"paragraph", "chapter"}

    assert client.delete(f"/api/mentions/{first}").status_code == 204
    assert client.delete(f"/api/mentions/{first}").status_code == 404
    lines = page_text(client, version_id, 8)["lines"]
    assert [m["mention_id"] for line in lines for m in line["mentions"]] == [second, second]


def test_tags_are_validated_like_any_anchor(
    client: TestClient, version_id: int, categories: dict[str, int]
) -> None:
    span = {**span_of(client, version_id, "single heron", 8), "exact": "other words"}
    refused = client.post(
        f"/api/versions/{version_id}/mentions",
        json={"span": span, "category_id": categories["animals"]},
    )
    assert refused.status_code == 400
    good = span_of(client, version_id, "single heron", 8)
    missing = client.post(
        f"/api/versions/{version_id}/mentions", json={"span": good, "category_id": 999}
    )
    assert missing.status_code == 404
    wrong = client.post(
        f"/api/versions/{version_id}/mentions",
        json={"span": good, "category_id": categories["animals"], "entity_id": 999},
    )
    assert wrong.status_code == 404


# ---- Narrative time ---------------------------------------------------------------


@pytest.fixture
def times(client: TestClient, version_id: int, categories: dict[str, int]) -> dict[str, int]:
    """Five time mentions across the book, in reading order."""
    time = categories["time"]
    return {
        "arrival": tag(client, version_id, "October, 1871", 7, category_id=time),
        "third": tag(client, version_id, "third day", 8, category_id=time),
        "rain": tag(client, version_id, "five days", 10, category_id=time),
        "sixth": tag(client, version_id, "sixth morning", 10, category_id=time),
        "weeks": tag(client, version_id, "Three weeks later", 11, category_id=time),
    }


def test_a_time_mention_has_no_entity_and_starts_without_a_value(
    client: TestClient, version_id: int, categories: dict[str, int], times: dict[str, int]
) -> None:
    assert index(client, version_id, category_id=categories["time"]) == []
    rows = chronology(client, version_id)
    assert [(r["mention_id"], r["page"], r["line_no"]) for r in rows] == [
        (times["arrival"], 7, 4),
        (times["third"], 8, 7),
        (times["rain"], 10, 3),
        (times["sixth"], 10, 5),
        (times["weeks"], 11, 9),
    ]
    assert all(r["kind"] is None and r["date_iso"] is None for r in rows)
    assert {r["problem"] for r in rows} == {"No value has been given yet."}


def test_the_chronology_resolves_each_point_and_follows_a_correction(
    client: TestClient, version_id: int, times: dict[str, int]
) -> None:
    set_time(client, times["arrival"], kind="absolute", at="1871-10-28", label="arrival")
    set_time(client, times["third"], kind="offset", offset="P2D")
    set_time(client, times["rain"], kind="offset", offset="P5D", remark="about a week")
    set_time(client, times["sixth"], kind="offset", offset="P1D", label="flood")
    set_time(client, times["weeks"], kind="offset", offset="P3W", relative_to_label="flood")

    rows = chronology(client, version_id)
    assert [(r["date_iso"], r["date_words"]) for r in rows] == [
        ("1871-10-28", "28 October 1871"),
        ("1871-10-30", "30 October 1871"),
        ("1871-11-04", "4 November 1871"),
        ("1871-11-05", "5 November 1871"),
        ("1871-11-26", "26 November 1871"),
    ]
    assert [r["problem"] for r in rows] == [None] * 5
    assert rows[2]["remark"] == "about a week"
    assert (rows[4]["offset"], rows[4]["relative_to_label"]) == ("P3W", "flood")
    # Time elapsed since each labeled point before it.
    assert rows[0]["since"] == []
    assert rows[3]["since"] == [{"label": "arrival", "iso": "P8D", "words": "8 days"}]
    assert rows[4]["since"] == [
        {"label": "arrival", "iso": "P29D", "words": "29 days"},
        {"label": "flood", "iso": "P21D", "words": "21 days"},
    ]

    # Correcting one value updates every point after it at once.
    set_time(client, times["arrival"], kind="absolute", at="1872-03-01", label="arrival")
    assert [r["date_iso"] for r in chronology(client, version_id)] == [
        "1872-03-01",
        "1872-03-03",
        "1872-03-08",
        "1872-03-09",
        "1872-03-30",
    ]


def test_dates_keep_the_precision_they_were_given(
    client: TestClient, version_id: int, times: dict[str, int]
) -> None:
    set_time(client, times["arrival"], kind="absolute", at="1871-10")
    set_time(client, times["third"], kind="offset", offset="P2D")
    set_time(client, times["weeks"], kind="offset", offset="P3W")
    rows = chronology(client, version_id)
    assert [rows[i]["date_words"] for i in (0, 1, 4)] == [
        "October 1871",
        "October 1871",
        "October 1871",
    ]
    set_time(client, times["arrival"], kind="absolute", at="1871-10-28T06:30")
    assert chronology(client, version_id)[1]["date_words"] == "30 October 1871, 06:30"


def test_a_chain_without_a_date_resolves_to_elapsed_time(
    client: TestClient, version_id: int, times: dict[str, int]
) -> None:
    set_time(client, times["third"], kind="offset", offset="P2D", label="start")
    set_time(client, times["rain"], kind="offset", offset="P5D")
    rows = chronology(client, version_id)
    assert (rows[1]["date_iso"], rows[1]["elapsed_words"]) == (None, "2 days")
    assert (rows[2]["date_iso"], rows[2]["elapsed_iso"], rows[2]["elapsed_words"]) == (
        None,
        "P7D",
        "7 days",
    )
    assert rows[2]["since"] == [{"label": "start", "iso": "P5D", "words": "5 days"}]


def test_a_value_can_be_cleared(client: TestClient, version_id: int, times: dict[str, int]) -> None:
    set_time(client, times["arrival"], kind="absolute", at="1871")
    assert client.delete(f"/api/mentions/{times['arrival']}/time").status_code == 204
    assert chronology(client, version_id)[0]["kind"] is None


@pytest.mark.parametrize(
    ("value", "status", "expected"),
    [
        ({"kind": "absolute", "at": "October 1871"}, 400, "Write the date"),
        ({"kind": "absolute"}, 400, "Write the date"),
        ({"kind": "offset", "offset": "five days"}, 400, "Write the offset"),
        (
            {"kind": "offset", "offset": "P5D", "relative_to_label": "nowhere"},
            400,
            "No time is labeled",
        ),
        ({"kind": "absolute", "at": "1871", "label": "Not A Label"}, 400, "label is"),
    ],
)
def test_bad_time_values_are_explained(
    client: TestClient, times: dict[str, int], value: dict[str, object], status: int, expected: str
) -> None:
    response = client.put(f"/api/mentions/{times['third']}/time", json=value)
    assert response.status_code == status
    assert expected in response.json()["detail"]


def test_labels_are_unique_and_a_time_cannot_count_from_itself(
    client: TestClient, times: dict[str, int]
) -> None:
    set_time(client, times["arrival"], kind="absolute", at="1871", label="arrival")
    taken = client.put(
        f"/api/mentions/{times['third']}/time",
        json={"kind": "absolute", "at": "1872", "label": "arrival"},
    )
    assert taken.status_code == 409
    set_time(
        client, times["third"], kind="offset", offset="P1D", relative_to_label="arrival", label="b"
    )
    circle = client.put(
        f"/api/mentions/{times['arrival']}/time",
        json={"kind": "offset", "offset": "P1D", "relative_to_label": "b", "label": "arrival"},
    )
    assert circle.status_code == 400
    assert "count from itself" in circle.json()["detail"]


def test_only_time_mentions_take_a_time(
    client: TestClient, version_id: int, categories: dict[str, int]
) -> None:
    place = tag(client, version_id, "Low Harbor", 7, category_id=categories["places"])
    refused = client.put(f"/api/mentions/{place}/time", json={"kind": "absolute", "at": "1871"})
    assert refused.status_code == 404


def test_a_time_can_be_given_when_tagging(
    client: TestClient, version_id: int, categories: dict[str, int]
) -> None:
    tag(
        client,
        version_id,
        "October, 1871",
        7,
        category_id=categories["time"],
        time={"kind": "absolute", "at": "1871-10", "label": "arrival"},
    )
    (row,) = chronology(client, version_id)
    assert (row["date_words"], row["label"]) == ("October 1871", "arrival")


def test_notes_show_the_narrative_date_at_their_place(
    client: TestClient, version_id: int, times: dict[str, int]
) -> None:
    types = {t["name"]: t["id"] for t in client.get("/api/note-types").json()}
    set_time(client, times["arrival"], kind="absolute", at="1871-10-28", label="arrival")
    set_time(client, times["third"], kind="offset", offset="P2D")
    set_time(client, times["rain"], kind="offset", offset="P5D")

    def forms(note: dict[str, Any]) -> list[tuple[str, object, object]]:
        return [
            (child["type"], child["attrs"].get("value"), child["attrs"]["broken"])
            for child in note["body"]["children"][0]["children"]
            if child["type"] in ("when", "since")
        ]

    body = "It is {{when}}, {{since:arrival}} after landing; {{since:nowhere}}."
    late = create(
        client,
        version_id,
        type_id=types["Comment"],
        body_md=body,
        span=span_of(client, version_id, "otters", 10),
    )
    assert forms(late) == [
        ("when", "4 November 1871", False),
        ("since", "7 days", False),
        ("since", None, True),
    ]
    early = create(
        client,
        version_id,
        type_id=types["Comment"],
        body_md=body,
        span=span_of(client, version_id, "single heron", 8),
    )
    assert forms(early)[:2] == [("when", "28 October 1871", False), ("since", "no time", False)]
    # Before any time point there is no date to show.
    first = create(
        client,
        version_id,
        type_id=types["Comment"],
        body_md="{{when}}",
        span=span_of(client, version_id, "The ferry came", 7),
    )
    assert forms(first) == [("when", None, True)]

    # Both are recomputed whenever a time value changes.
    set_time(client, times["arrival"], kind="absolute", at="1872-03-01", label="arrival")
    again = client.get(f"/api/notes/{late['id']}").json()
    assert forms(again)[:2] == [("when", "8 March 1872", False), ("since", "7 days", False)]
    # The live preview works them out for the note being edited.
    preview = client.post(
        "/api/notes/render",
        json={"body_md": "{{when}}", "version_id": version_id, "note_id": late["id"]},
    ).json()
    assert preview["body"]["children"][0]["children"][0]["attrs"]["value"] == "8 March 1872"


def test_legacy_time_tags_arrive_without_values(client: TestClient, version_id: int) -> None:
    client.post(f"/api/versions/{version_id}/imports/commentary", json=COMMENTARY)
    rows = chronology(client, version_id)
    assert [(r["page"], r["line_no"], r["kind"]) for r in rows] == [(7, 4, None), (8, 7, None)]
    todo = client.get(f"/api/versions/{version_id}/todo").json()
    assert [(t["page"], t["line_no"]) for t in todo["times_without_value"]] == [(7, 4), (8, 7)]
    set_time(client, rows[0]["mention_id"], kind="absolute", at="1871-10")
    todo = client.get(f"/api/versions/{version_id}/todo").json()
    assert [(t["page"], t["line_no"]) for t in todo["times_without_value"]] == [(8, 7)]


def test_mentions_and_time_points_export_as_data_without_the_text(
    client: TestClient, version_id: int
) -> None:
    client.post(f"/api/versions/{version_id}/imports/commentary", json=COMMENTARY)
    first = chronology(client, version_id)[0]["mention_id"]
    set_time(client, first, kind="absolute", at="1871-10", label="arrival")
    response = client.get(f"/api/versions/{version_id}/entities/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert (data["work"], data["title"]) == ("fx", "The Fixture Book")
    by_name = {(e["category"], e["name"]): e for e in data["entities"]}
    assert by_name[("places", "Low Harbor")]["mentions"] == [
        {"page": 7, "line": 1},
        {"page": 7, "line": 3},
    ]
    assert by_name[("numbers", "forty-six")]["value"] == "46"
    assert data["time_points"] == [
        {
            "page": 7,
            "line": 4,
            "kind": "absolute",
            "at": "1871-10",
            "offset": None,
            "relative_to": None,
            "label": "arrival",
            "remark": "",
            "resolved": "1871-10",
            "elapsed": None,
            "since": {},
        },
        {
            "page": 8,
            "line": 7,
            "kind": None,
            "at": None,
            "offset": None,
            "relative_to": None,
            "label": None,
            "remark": "",
            "resolved": None,
            "elapsed": None,
            "since": {},
        },
    ]
    # Entity names are the author's index terms; no line of the book is in the export.
    for number in (7, 8, 9, 12):
        for line in page_text(client, version_id, number)["lines"]:
            if line["line_no"] is not None and len(line["text"]) > 20:
                assert line["text"] not in response.text
