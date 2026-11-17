import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type {
  Category,
  ChronologyRow,
  Entity,
  Figure,
  NoteSummary,
  NoteType,
  TodoList,
} from "../src/api/client";
import { App } from "../src/App";
import { forgetPrefs, mockServer, renderWithQuery, type Sent, setUrl, TYPES, VERSION } from "./helpers";

beforeEach(forgetPrefs);
afterEach(cleanup);

const CATEGORIES: Category[] = [
  { id: 1, name: "places", color: "#5b8c85", sort: 10, is_time: false },
  { id: 2, name: "animals", color: "#b07a4a", sort: 20, is_time: false },
  { id: 5, name: "time", color: "#a86a7a", sort: 50, is_time: true },
];

const ENTITIES: Entity[] = [
  { id: 10, category_id: 1, name: "Low Harbor", value: null, places: [{ page: 7, line_no: 1 }, { page: 9, line_no: 8 }] },
  { id: 20, category_id: 2, name: "gulls", value: null, places: [{ page: 7, line_no: 4 }] },
  { id: 21, category_id: 2, name: "heron", value: "Ardea", places: [{ page: 8, line_no: 3 }] },
];

type Handlers = Parameters<typeof mockServer>[0];

function open(view: string, handlers: Handlers) {
  const server = mockServer({
    "GET /api/versions/1": () => ({ body: VERSION }),
    "GET /api/note-types": () => ({ body: TYPES }),
    ...handlers,
  });
  setUrl(`/v/1/${view}`);
  renderWithQuery(<App />);
  return server;
}

function changes(sent: Sent[]): [string, string, unknown][] {
  return sent.map((request) => [request.method, request.path, request.body]);
}

describe("the views in the sidebar", () => {
  it("links every view, marks the current one, and leads back to the text", async () => {
    open("todo", { "GET /api/versions/1/todo": () => ({ body: EMPTY_TODO }) });
    const nav = await screen.findByRole("complementary", { name: "Chapters and views" });
    await waitFor(() => expect(within(nav).getAllByRole("link").length).toBeGreaterThan(6));
    const links = within(nav).getAllByRole("link").map((link) => [link.textContent, link.getAttribute("href")]);
    expect(links.slice(2)).toEqual([
      ["Review", "/v/1/review"],
      ["To-do", "/v/1/todo"],
      ["Entities", "/v/1/entities"],
      ["Chronology", "/v/1/chronology"],
      ["Figures", "/v/1/figures"],
      ["Note types", "/v/1/types"],
    ]);
    expect(within(nav).getByRole("link", { name: "To-do" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Back to the text" }).getAttribute("href")).toBe("/v/1/p/7");
    fireEvent.click(within(nav).getByRole("link", { name: "Review" }));
    expect(await screen.findByRole("heading", { name: "Review", level: 1 })).toBeTruthy();
  });
});

describe("the entities view", () => {
  const handlers: Handlers = {
    "GET /api/entity-categories": () => ({ body: CATEGORIES }),
    "GET /api/versions/1/entities": () => ({ body: ENTITIES }),
    "PATCH /api/entities/21": () => ({ status: 204, body: null }),
    "POST /api/entities/20/merge": () => ({ status: 204, body: null }),
    "POST /api/entity-categories": () => ({ status: 201, body: CATEGORIES[0] }),
    "PATCH /api/entity-categories/2": () => ({ body: CATEGORIES[1] }),
    "POST /api/entity-categories/2/merge": () => ({ status: 204, body: null }),
  };

  it("lists each category's entities with every page they occur on", async () => {
    open("entities", handlers);
    const places = await screen.findByRole("region", { name: "places" });
    expect(within(places).getByLabelText("Name of Low Harbor")).toHaveProperty("value", "Low Harbor");
    const pages = within(places).getAllByRole("link").map((link) => [link.textContent, link.getAttribute("href")]);
    expect(pages).toEqual([
      ["7", "/v/1/p/7#l1"],
      ["9", "/v/1/p/9#l8"],
    ]);
    const animals = screen.getByRole("region", { name: "animals" });
    expect(within(animals).getByLabelText("Value of heron")).toHaveProperty("value", "Ardea");
    // Times have dates, not entries.
    expect(within(screen.getByRole("region", { name: "time" })).getByRole("link", { name: "chronology" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Download mentions and times as data" }).getAttribute("href")).toBe(
      "/api/versions/1/entities/export",
    );
  });

  it("renames an entry, gives it a value, and merges it into another", async () => {
    const { sent } = open("entities", handlers);
    const name = await screen.findByLabelText("Name of heron");
    fireEvent.change(name, { target: { value: "grey heron" } });
    fireEvent.blur(name);
    const value = screen.getByLabelText("Value of heron");
    fireEvent.change(value, { target: { value: "" } });
    fireEvent.blur(value);
    fireEvent.change(screen.getByLabelText("Merge gulls into"), { target: { value: "21" } });
    await waitFor(() => expect(sent.length).toBe(3));
    expect(changes(sent)).toEqual([
      ["PATCH", "/api/entities/21", { name: "grey heron" }],
      ["PATCH", "/api/entities/21", { value: "" }],
      ["POST", "/api/entities/20/merge", { into_id: 21 }],
    ]);
  });

  it("adds, renames, recolors and merges categories", async () => {
    const { sent } = open("entities", handlers);
    fireEvent.change(await screen.findByLabelText("New category"), { target: { value: "weather" } });
    fireEvent.click(screen.getByRole("button", { name: "Add category" }));
    const name = screen.getByLabelText("Name of the category animals");
    fireEvent.change(name, { target: { value: "beasts" } });
    fireEvent.blur(name);
    fireEvent.change(screen.getByLabelText("Color of animals"), { target: { value: "#112233" } });
    fireEvent.change(screen.getByLabelText("Merge animals into"), { target: { value: "1" } });
    await waitFor(() => expect(sent.length).toBe(4));
    expect(changes(sent)).toEqual([
      ["POST", "/api/entity-categories", { name: "weather" }],
      ["PATCH", "/api/entity-categories/2", { name: "beasts" }],
      ["PATCH", "/api/entity-categories/2", { color: "#112233" }],
      ["POST", "/api/entity-categories/2/merge", { into_id: 1 }],
    ]);
    // The time category cannot be merged away.
    expect(screen.queryByLabelText("Merge time into")).toBeNull();
  });
});

const row = (overrides: Partial<ChronologyRow>): ChronologyRow => ({
  mention_id: 1,
  page: 7,
  line_no: 4,
  kind: null,
  at: null,
  offset: null,
  relative_to_label: null,
  label: null,
  remark: "",
  date_iso: null,
  date_words: null,
  elapsed_iso: null,
  elapsed_words: null,
  problem: null,
  since: [],
  ...overrides,
});

describe("the chronology", () => {
  const rows = [
    row({ mention_id: 1, kind: "absolute", at: "1871-10-28", label: "arrival", date_iso: "1871-10-28", date_words: "28 October 1871" }),
    row({
      mention_id: 2, page: 10, line_no: 3, kind: "offset", offset: "P7D",
      date_iso: "1871-11-04", date_words: "4 November 1871",
      since: [{ label: "arrival", iso: "P7D", words: "7 days" }],
    }),
    row({ mention_id: 3, page: 11, line_no: 9, problem: "No value has been given yet." }),
  ];
  const handlers: Handlers = {
    "GET /api/versions/1/chronology": () => ({ body: rows }),
    "PUT /api/mentions/3/time": () => ({ status: 204, body: null }),
    "DELETE /api/mentions/2/time": () => ({ status: 204, body: null }),
  };

  it("lists every time point in reading order with what it resolves to", async () => {
    open("chronology", handlers);
    const table = await screen.findByRole("table");
    const body = within(table).getAllByRole("row").slice(1);
    expect(body.map((item) => within(item).getAllByRole("cell")[0]?.textContent)).toEqual(["7.4", "10.3", "11.9"]);
    expect(within(body[0] as HTMLElement).getByText("28 October 1871")).toBeTruthy();
    expect(within(body[1] as HTMLElement).getByText("4 November 1871")).toBeTruthy();
    expect((body[1] as HTMLElement).textContent).toContain("7 days since arrival");
    expect(within(body[2] as HTMLElement).getByText("No value has been given yet.")).toBeTruthy();
    expect(within(body[0] as HTMLElement).getByRole("link", { name: "7.4" }).getAttribute("href")).toBe("/v/1/p/7#l4");
  });

  it("gives a time its value as an offset from a labeled time", async () => {
    const { sent } = open("chronology", handlers);
    const form = await screen.findByRole("form", { name: "Time at 11.9" });
    fireEvent.change(within(form).getByLabelText("Kind"), { target: { value: "offset" } });
    fireEvent.change(within(form).getByLabelText("Offset"), { target: { value: "P3W" } });
    // Other labeled times are offered to count from.
    const from = within(form).getByLabelText("Counts from");
    expect(within(from).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "The time before it",
      "arrival",
    ]);
    fireEvent.change(from, { target: { value: "arrival" } });
    fireEvent.change(within(form).getByLabelText("Label"), { target: { value: "return" } });
    fireEvent.change(within(form).getByLabelText("Remark"), { target: { value: "about three weeks" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent.length).toBe(1));
    expect(changes(sent)).toEqual([
      [
        "PUT",
        "/api/mentions/3/time",
        { kind: "offset", at: null, offset: "P3W", relative_to_label: "arrival", label: "return", remark: "about three weeks" },
      ],
    ]);
  });

  it("clears a value by setting it back to none", async () => {
    const { sent } = open("chronology", handlers);
    const form = await screen.findByRole("form", { name: "Time at 10.3" });
    fireEvent.change(within(form).getByLabelText("Kind"), { target: { value: "" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(changes(sent)).toEqual([["DELETE", "/api/mentions/2/time", undefined]]));
  });

  it("explains what to do when no times are tagged", async () => {
    open("chronology", { "GET /api/versions/1/chronology": () => ({ body: [] }) });
    expect(await screen.findByText(/No times are tagged yet/)).toBeTruthy();
  });
});

describe("the figures view", () => {
  const figures: Figure[] = [
    {
      id: 1, label: "harbor", file: "harbor.png", caption: "The harbor", credit: "A. Quill", has_file: true,
      uses: [
        { note_id: 4, type_id: 2, version_id: 1, page: 7, line_no: 9, placed: true },
        { note_id: 9, type_id: 2, version_id: 1, page: 10, line_no: 2, placed: false },
      ],
    },
    { id: 2, label: "spare", file: "", caption: "", credit: "", has_file: false, uses: [] },
  ];
  const handlers: Handlers = {
    "GET /api/figures": () => ({ body: figures }),
    "POST /api/figures": () => ({ status: 201, body: figures[1] }),
    "PATCH /api/figures/1": () => ({ body: figures[0] }),
    "PUT /api/figures/2/image": () => ({ body: figures[1] }),
    "DELETE /api/figures/2": () => ({ status: 204, body: null }),
  };

  it("shows each figure with its image, where it is used, and which are unused", async () => {
    open("figures", handlers);
    const harbor = await screen.findByRole("listitem", { name: "Figure harbor" });
    expect(within(harbor).getByRole("img").getAttribute("src")).toBe("/api/figures/harbor/file?v=harbor.png");
    expect(within(harbor).getAllByRole("link").map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["p. 7", "/v/1/p/7#l9"],
      ["p. 10 (cited)", "/v/1/p/10#l2"],
    ]);
    const spare = screen.getByRole("listitem", { name: "Figure spare" });
    expect(within(spare).getByText("Unused")).toBeTruthy();
    expect(within(spare).getByText("No image yet")).toBeTruthy();
    expect(within(spare).queryByRole("img")).toBeNull();
  });

  it("adds a figure, uploads its image, edits it, and deletes after a second press", async () => {
    const { sent } = open("figures", handlers);
    const form = await screen.findByRole("form", { name: "New figure" });
    fireEvent.change(within(form).getByLabelText("Label"), { target: { value: "tang" } });
    fireEvent.change(within(form).getByLabelText("Caption"), { target: { value: "A map" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add figure" }));

    const image = new File([new Uint8Array([1, 2, 3])], "map.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Image for spare"), { target: { files: [image] } });

    const caption = screen.getByLabelText("Caption of harbor");
    fireEvent.change(caption, { target: { value: "Low water" } });
    fireEvent.blur(caption);

    const spare = screen.getByRole("listitem", { name: "Figure spare" });
    fireEvent.click(within(spare).getByRole("button", { name: "Delete" }));
    expect(sent.some((request) => request.method === "DELETE")).toBe(false);
    fireEvent.click(within(spare).getByRole("button", { name: "Really delete spare" }));

    await waitFor(() => expect(sent.length).toBe(4));
    expect(changes(sent).map(([method, path]) => [method, path])).toEqual([
      ["POST", "/api/figures"],
      ["PUT", "/api/figures/2/image"],
      ["PATCH", "/api/figures/1"],
      ["DELETE", "/api/figures/2"],
    ]);
    expect(sent[0]?.body).toEqual({ label: "tang", caption: "A map", credit: "" });
    // The image is sent as it is, as the body of the request.
    expect(sent[1]?.body).toBeInstanceOf(Blob);
    expect((sent[1]?.body as Blob).type).toBe("image/png");
    expect(sent[2]?.body).toEqual({ caption: "Low water" });
  });
});

const summary = (overrides: Partial<NoteSummary>): NoteSummary => ({
  id: 1,
  type_id: 2,
  scope: "span",
  level: 1,
  status: "draft",
  tags: [],
  page: 7,
  line_no: 3,
  excerpt: "A first remark.",
  ...overrides,
});

describe("the review view", () => {
  const all = [
    summary({ id: 1 }),
    summary({ id: 2, type_id: 1, level: 2, page: 8, line_no: 9, excerpt: "For re-readers.", tags: ["tides"] }),
    summary({ id: 3, scope: "page", page: 9, line_no: null, excerpt: "" }),
  ];
  const handlers: Handlers = {
    "GET /api/tags": () => ({ body: ["tides"] }),
    "GET /api/versions/1/notes": (request) => ({
      body: all.filter(
        (note) =>
          (!request.query.type_id || String(note.type_id) === request.query.type_id) &&
          (!request.query.level || String(note.level) === request.query.level),
      ),
    }),
    "POST /api/versions/1/notes/status": () => ({ body: { changed: 2 } }),
  };

  it("lists notes with place, type, level, status and how they begin", async () => {
    open("review", handlers);
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((item) => within(item).getAllByRole("cell").slice(1).map((cell) => cell.textContent))).toEqual([
      ["p. 7.3", "Comment", "First reading", "Draft", "A first remark."],
      ["p. 8.9", "Clarification", "Have read", "Draft", "For re-readers. #tides"],
      ["p. 9", "Comment", "First reading", "Draft", "Highlight only"],
    ]);
    expect(within(rows[0] as HTMLElement).getByRole("link").getAttribute("href")).toBe("/v/1/p/7#l3");
  });

  it("filters by chapter, type, level, status and tag", async () => {
    const { fetchMock } = open("review", handlers);
    await screen.findByRole("table");
    const filters = screen.getByRole("group", { name: "Filters" });
    fireEvent.change(within(filters).getByLabelText("Type"), { target: { value: "1" } });
    await waitFor(() => expect(screen.getAllByRole("row").length).toBe(2));
    fireEvent.change(within(filters).getByLabelText("Chapter"), { target: { value: "2" } });
    fireEvent.change(within(filters).getByLabelText("Level"), { target: { value: "2" } });
    fireEvent.change(within(filters).getByLabelText("Status"), { target: { value: "draft" } });
    fireEvent.change(within(filters).getByLabelText("Tag"), { target: { value: "tides" } });
    await waitFor(() => {
      const asked = fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes("/notes?"));
      expect(asked.at(-1)).toBe(
        "/api/versions/1/notes?division_id=2&type_id=1&level=2&status=draft&tag=tides",
      );
    });
  });

  it("marks the selected notes ready in one go", async () => {
    const { sent } = open("review", handlers);
    await screen.findByRole("table");
    const bulk = screen.getByRole("group", { name: "Selected notes" });
    expect((within(bulk).getByRole("button", { name: "Mark ready" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Select the note at p. 7.3"));
    fireEvent.click(screen.getByLabelText("Select the note at p. 9"));
    expect(bulk.textContent).toContain("3 notes, 2 selected");
    fireEvent.click(within(bulk).getByRole("button", { name: "Mark ready" }));
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toEqual({ note_ids: [1, 3], status: "ready" });

    fireEvent.click(within(bulk).getByRole("button", { name: "Select all" }));
    fireEvent.click(within(bulk).getByRole("button", { name: "Mark draft" }));
    await waitFor(() => expect(sent.length).toBe(2));
    expect(sent[1]?.body).toEqual({ note_ids: [1, 2, 3], status: "draft" });
  });
});

const EMPTY_TODO: TodoList = {
  remarks: [],
  drafts: [],
  broken_references: [],
  orphaned: [],
  unused_figures: [],
  times_without_value: [],
};

describe("the to-do list", () => {
  it("gathers remarks, times without a value, broken references, unused figures and drafts", async () => {
    const todo: TodoList = {
      remarks: [{ note: summary({ id: 1 }), text: "check the date" }],
      drafts: [summary({ id: 1 }), summary({ id: 2, page: 8, line_no: 9, excerpt: "" })],
      broken_references: [{ note: summary({ id: 2, page: 8, line_no: 9 }), form: "{{fx:99}}" }],
      orphaned: [],
      unused_figures: [{ id: 2, label: "spare", caption: "Never placed" }],
      times_without_value: [{ mention_id: 3, page: 11, line_no: 9 }],
    };
    open("todo", { "GET /api/versions/1/todo": () => ({ body: todo }) });
    const remarks = await screen.findByRole("region", { name: "Remarks" });
    expect(within(remarks).getByRole("listitem").textContent).toBe("Comment, p. 7.3: check the date");
    expect(within(remarks).getByRole("link").getAttribute("href")).toBe("/v/1/p/7#l3");
    expect(screen.getByRole("region", { name: "Times without a value" }).textContent).toContain("p. 11.9");
    expect(screen.getByRole("region", { name: "Broken references" }).textContent).toContain("{{fx:99}}");
    expect(screen.getByRole("region", { name: "Unused figures" }).textContent).toContain("spare: Never placed");
    expect(within(screen.getByRole("region", { name: "Draft notes" })).getAllByRole("listitem").length).toBe(2);
    expect(screen.getByRole("region", { name: "Notes that lost their place" }).textContent).toContain("Nothing here.");
    expect(screen.getByRole("heading", { name: "Draft notes (2)" })).toBeTruthy();
  });
});

describe("note types", () => {
  const handlers: Handlers = {
    "POST /api/note-types": () => ({ status: 201, body: TYPES[0] }),
    "PATCH /api/note-types/2": () => ({ body: TYPES[1] }),
    "POST /api/note-types/2/merge": () => ({ status: 204, body: null }),
  };

  it("adds, renames, recolors and merges note types", async () => {
    const { sent } = open("types", handlers);
    const name = await screen.findByLabelText("Name of Comment");
    fireEvent.change(name, { target: { value: "Remark" } });
    fireEvent.blur(name);
    fireEvent.change(screen.getByLabelText("Color of Comment"), { target: { value: "#123456" } });
    fireEvent.change(screen.getByLabelText("Kind of Comment"), { target: { value: "definition" } });
    fireEvent.change(screen.getByLabelText("Merge Comment into"), { target: { value: "1" } });

    const form = screen.getByRole("form", { name: "New note type" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Geography" } });
    fireEvent.change(within(form).getByLabelText("Code"), { target: { value: "g" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add note type" }));

    await waitFor(() => expect(sent.length).toBe(5));
    expect(changes(sent)).toEqual([
      ["PATCH", "/api/note-types/2", { name: "Remark" }],
      ["PATCH", "/api/note-types/2", { color: "#123456" }],
      ["PATCH", "/api/note-types/2", { role: "definition" }],
      ["POST", "/api/note-types/2/merge", { into_id: 1 }],
      ["POST", "/api/note-types", { name: "Geography", code: "g", color: "#7a8a9a", role: "note" }],
    ]);
  });

  it("shows the server's explanation when a change is refused", async () => {
    open("types", {
      "PATCH /api/note-types/2": () => ({
        status: 409,
        body: { detail: "There is already a note type called Clarification." },
      }),
    });
    const name = await screen.findByLabelText("Name of Comment");
    fireEvent.change(name, { target: { value: "Clarification" } });
    fireEvent.blur(name);
    expect((await screen.findByRole("alert")).textContent).toContain("already a note type called Clarification");
  });

  it("lists the types that exist", async () => {
    open("types", {});
    await screen.findByLabelText("Name of Comment");
    const names = (TYPES as NoteType[]).map((type) => screen.getByLabelText(`Name of ${type.name}`));
    expect(names.length).toBe(3);
  });
});
