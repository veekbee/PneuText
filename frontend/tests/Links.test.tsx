import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Backlink, Note, PageLinks, PageText, SearchResults } from "../src/api/client";
import { App } from "../src/App";
import { cancelLink } from "../src/lib/linkTray";
import {
  bodyOf,
  forgetPrefs,
  line,
  mockApi,
  noteOf,
  renderWithQuery,
  selectText,
  setUrl,
  TYPES,
  VERSION,
} from "./helpers";

beforeEach(() => {
  forgetPrefs();
  cancelLink();
});
afterEach(cleanup);

function pageText(page: number, first: string, second: string): PageText {
  return {
    version_id: 1,
    edit_seq: 0,
    page,
    prev_page: page > 7 ? page - 1 : null,
    next_page: page < 9 ? page + 1 : null,
    division: VERSION.divisions[0] ?? null,
    lines: [
      line(first, { id: page * 10 + 1, segment_id: page, start_offset: 0, line_no: 1, starts_paragraph: true }),
      line(second, { id: page * 10 + 2, segment_id: page, start_offset: 30, line_no: 2, ends_paragraph: true }),
    ],
  };
}

const backlink = (overrides: Partial<Backlink> = {}): Backlink => ({
  note_id: 90,
  type_id: 2,
  level: 1,
  status: "draft",
  page: 9,
  line_no: 4,
  target: "p. 7.2",
  ...overrides,
});

interface World {
  notes?: Note[];
  links?: PageLinks;
  search?: (query: string, corpus: boolean) => SearchResults;
  figures?: unknown[];
}

function mockWorld(world: World = {}) {
  const sent: { method: string; url: string; body: unknown }[] = [];
  const empty: PageLinks = { backlinks: [], passages: [] };
  const handlers: Parameters<typeof mockApi>[0] = {
    "GET /api/versions/1": () => ({ body: VERSION }),
    "GET /api/note-types": () => ({ body: TYPES }),
    "GET /api/figures": () => ({ body: world.figures ?? [] }),
    "GET /api/versions/1/pages/7/text": () => ({ body: pageText(7, "alpha beta gamma", "delta epsilon") }),
    "GET /api/versions/1/pages/8/text": () => ({ body: pageText(8, "zeta eta theta", "iota kappa") }),
    "GET /api/versions/1/pages/7/notes": () => ({ body: world.notes ?? [] }),
    "GET /api/versions/1/pages/8/notes": () => ({ body: [] }),
    "GET /api/versions/1/pages/7/links": () => ({ body: world.links ?? empty }),
    "GET /api/versions/1/pages/8/links": () => ({ body: empty }),
    "POST /api/versions/1/links": (body) => {
      sent.push({ method: "POST", url: "/api/versions/1/links", body });
      return { status: 201, body: { id: 5 } };
    },
    "DELETE /api/links/5": () => {
      sent.push({ method: "DELETE", url: "/api/links/5", body: null });
      return { status: 204, body: null };
    },
    "POST /api/notes/render": (body) => ({
      body: { body: bodyOf(`previewed: ${(body as { body_md: string }).body_md}`) },
    }),
    "PATCH /api/notes/41": (body) => {
      sent.push({ method: "PATCH", url: "/api/notes/41", body });
      return { body: noteOf(41) };
    },
  };
  const fetchMock = mockApi(handlers).mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const key = `${method} ${url}`;
    if (url.startsWith("/api/versions/1/search")) {
      const params = new URL(url, "http://local").searchParams;
      const query = params.get("q") ?? "";
      const corpus = params.get("corpus") === "true";
      sent.push({ method, url, body: null });
      const results = world.search?.(query, corpus) ?? {
        query,
        reference: null,
        corpus: corpus ? [] : null,
        notes: [],
      };
      return new Response(JSON.stringify(results));
    }
    const handler = handlers[key];
    if (handler === undefined) return new Response(JSON.stringify({ detail: `none for ${key}` }), { status: 404 });
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    const answer = handler(body);
    return new Response(answer.status === 204 ? null : JSON.stringify(answer.body), {
      status: answer.status ?? 200,
    });
  });
  return { sent, fetchMock };
}

async function openPage(page = 7): Promise<HTMLElement> {
  setUrl(`/v/1/p/${page}`);
  renderWithQuery(<App />);
  return screen.findByLabelText(`Page ${page}`);
}

function rowText(page: HTMLElement, lineNo: number): Text {
  const row = page.querySelector(`#l${lineNo}`) as HTMLElement;
  return [...row.childNodes].find((node) => node.nodeType === Node.TEXT_NODE) as Text;
}

describe("backlinks", () => {
  const links: PageLinks = {
    backlinks: [backlink(), backlink({ note_id: 91, type_id: 1, level: 2, page: 8, line_no: 1, target: "p. 7" })],
    passages: [],
  };

  it("lists the notes that refer to the page, each with its type and place", async () => {
    mockWorld({ links });
    await openPage();
    const section = await screen.findByRole("region", { name: "Referred to from" });
    const items = within(section).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Comment, p. 9.4 cites p. 7.2",
      "Clarification, p. 8.1 cites p. 7",
    ]);
    expect(within(section).getByRole("link", { name: "Comment, p. 9.4" }).getAttribute("href")).toBe(
      "/v/1/p/9#l4",
    );
  });

  it("hides a backlink that comes from a level 2 note on a first reading", async () => {
    mockWorld({ links });
    await openPage();
    const section = await screen.findByRole("region", { name: "Referred to from" });
    fireEvent.click(screen.getByRole("button", { name: "First reading" }));
    expect(within(section).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Comment, p. 9.4 cites p. 7.2",
    ]);
  });

  it("lists under a note the notes that refer to it", async () => {
    mockWorld({
      notes: [
        noteOf(41, {
          body_md: "The instrument.",
          body: bodyOf("The instrument."),
          backlinks: [backlink({ note_id: 92, page: 8, line_no: 2, target: null })],
        }),
      ],
    });
    await openPage();
    const card = (await screen.findByText("The instrument.")).closest(".note-card") as HTMLElement;
    const section = within(card).getByRole("region", { name: "Referred to by" });
    expect(within(section).getByRole("link", { name: "Comment, p. 8.2" }).getAttribute("href")).toBe(
      "/v/1/p/8#l2",
    );
  });
});

describe("linking one passage to another", () => {
  it("keeps the first passage in a tray across pages, then links it to the second", async () => {
    const { sent } = mockWorld();
    const page = await openPage();
    await screen.findByText("alpha beta gamma");
    selectText(rowText(page, 1), 6, rowText(page, 1), 10);
    fireEvent.click(within(await screen.findByRole("dialog", { name: "Selection" })).getByRole("button", { name: "Link" }));

    const tray = screen.getByRole("status", { name: "Link in progress" });
    expect(tray.textContent).toContain("Linking from p. 7.1");
    expect(sent).toEqual([]);

    // The tray stays while the reader turns the page.
    fireEvent.keyDown(window, { key: "ArrowRight" });
    const next = await screen.findByLabelText("Page 8");
    await screen.findByText("zeta eta theta");
    expect(screen.getByRole("status", { name: "Link in progress" })).toBeTruthy();

    selectText(rowText(next, 2), 0, rowText(next, 2), 4);
    fireEvent.click(
      within(await screen.findByRole("dialog", { name: "Selection" })).getByRole("button", { name: "Link here" }),
    );
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toEqual({
      source: { start_segment_id: 7, start_offset: 6, end_segment_id: 7, end_offset: 10, exact: "beta" },
      target: { start_segment_id: 8, start_offset: 30, end_segment_id: 8, end_offset: 34, exact: "iota" },
    });
    await waitFor(() => expect(screen.queryByRole("status", { name: "Link in progress" })).toBeNull());
  });

  it("starts and completes a link with the l key, and cancels one with Escape", async () => {
    const { sent } = mockWorld();
    const page = await openPage();
    await screen.findByText("alpha beta gamma");
    selectText(rowText(page, 1), 0, rowText(page, 1), 5);
    await screen.findByRole("dialog", { name: "Selection" });
    fireEvent.keyDown(window, { key: "l" });
    expect(screen.getByRole("status", { name: "Link in progress" })).toBeTruthy();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("status", { name: "Link in progress" })).toBeNull();
    expect(sent).toEqual([]);
  });

  it("lists linked passages with the far end as a link, and removes one on request", async () => {
    const { sent } = mockWorld({
      links: {
        backlinks: [],
        passages: [
          {
            id: 5,
            relation: "related",
            source: { page: 7, line_no: 1, end_page: 7, end_line_no: 1, here: true },
            target: { page: 9, line_no: 3, end_page: 9, end_line_no: 4, here: false },
          },
        ],
      },
    });
    await openPage();
    const section = await screen.findByRole("region", { name: "Linked passages" });
    expect(within(section).getByRole("link", { name: "p. 9.3" }).getAttribute("href")).toBe("/v/1/p/9#l3");
    fireEvent.click(within(section).getByRole("button", { name: "Remove the link to p. 9.3" }));
    await waitFor(() => expect(sent).toEqual([{ method: "DELETE", url: "/api/links/5", body: null }]));
  });
});

describe("search", () => {
  const found = (query: string, corpus: boolean): SearchResults => ({
    query,
    reference: query === "8.2" ? { page: 8, line_no: 2 } : null,
    corpus: corpus
      ? [{ page: 8, line_no: 1, before: "zeta ", match: "eta", after: " theta" }]
      : null,
    notes: [
      { note_id: 41, type_id: 2, level: 1, status: "draft", page: 7, line_no: 1, excerpt: "An eta remark." },
      { note_id: 42, type_id: 1, level: 2, status: "draft", page: 8, line_no: 2, excerpt: "For re-readers: eta." },
    ],
  });

  it("looks in the text and in notes separately, and goes to a hit", async () => {
    const { sent } = mockWorld({ search: found });
    await openPage();
    await screen.findByText("alpha beta gamma");
    fireEvent.keyDown(window, { key: "/" });
    const box = screen.getByRole("searchbox", { name: "Search" });
    expect(document.activeElement).toBe(box);
    fireEvent.change(box, { target: { value: "eta" } });

    const results = await screen.findByRole("region", { name: "Search results" });
    const inText = within(results).getByRole("region", { name: "In the text" });
    expect(within(inText).getByRole("button").textContent).toBe("8.1zeta eta theta");
    expect(within(inText).getByText("eta", { selector: "mark" })).toBeTruthy();
    const inNotes = within(results).getByRole("region", { name: "In notes" });
    expect(within(inNotes).getAllByRole("button").map((item) => item.textContent)).toEqual([
      "Comment, p. 7An eta remark.",
      "Clarification, p. 8For re-readers: eta.",
    ]);
    expect(sent.at(-1)?.url).toBe("/api/versions/1/search?q=eta&corpus=true");

    fireEvent.click(within(inText).getByRole("button"));
    expect(await screen.findByLabelText("Page 8")).toBeTruthy();
    expect(window.location.pathname + window.location.hash).toBe("/v/1/p/8#l1");
    expect(screen.queryByRole("region", { name: "Search results" })).toBeNull();
  });

  it("follows a page reference on Enter", async () => {
    mockWorld({ search: found });
    await openPage();
    const box = screen.getByRole("searchbox", { name: "Search" });
    fireEvent.change(box, { target: { value: "8.2" } });
    const results = await screen.findByRole("region", { name: "Search results" });
    expect(within(results).getByRole("region", { name: "Go to" }).textContent).toContain("Page 8, line 2");
    fireEvent.submit(box);
    await screen.findByLabelText("Page 8");
    expect(window.location.hash).toBe("#l2");
  });

  it("does not search the text in blank mode, and says so", async () => {
    window.localStorage.setItem("pneutext.prefs", JSON.stringify({ mode: "blank" }));
    const { sent } = mockWorld({ search: found });
    setUrl("/v/1/p/7");
    renderWithQuery(<App />);
    fireEvent.change(await screen.findByRole("searchbox", { name: "Search" }), { target: { value: "eta" } });
    const results = await screen.findByRole("region", { name: "Search results" });
    expect(within(results).queryByRole("region", { name: "In the text" })).toBeNull();
    expect(within(results).getByText("The text itself is not searched in blank mode.")).toBeTruthy();
    expect(within(results).getByRole("region", { name: "In notes" })).toBeTruthy();
    const searches = sent.filter((request) => request.url.includes("/search"));
    expect(searches.every((request) => request.url.endsWith("corpus=false"))).toBe(true);
  });

  it("hides level 2 notes from the results on a first reading", async () => {
    window.localStorage.setItem("pneutext.prefs", JSON.stringify({ level: "first" }));
    mockWorld({ search: found });
    await openPage();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search" }), { target: { value: "eta" } });
    const inNotes = await screen.findByRole("region", { name: "In notes" });
    expect(within(inNotes).getAllByRole("button").length).toBe(1);
  });
});

describe("the reference picker", () => {
  const notes = [
    noteOf(41, { body_md: "First words", body: bodyOf("First words") }),
    noteOf(43, { type_id: 1, body_md: "A second note", body: bodyOf("A second note"), start: { page: 7, line_no: 2 } }),
  ];
  const figures = [{ id: 1, label: "harbor", file: "harbor.png", caption: "The harbor", credit: "", has_file: true }];

  async function openEditor(): Promise<HTMLElement> {
    mockWorld({ notes, figures });
    await openPage();
    const card = (await screen.findByText("First words")).closest(".note-card") as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Edit" }));
    return within(card).getByRole("form", { name: "Edit note" });
  }

  it("inserts a page or line reference where the cursor is", async () => {
    const form = await openEditor();
    const body = within(form).getByLabelText("Note") as HTMLTextAreaElement;
    body.setSelectionRange(5, 5);
    const place = within(form).getByLabelText("Page or lines");
    fireEvent.change(place, { target: { value: "10.3 - 11.1" } });
    fireEvent.click(within(form).getByRole("button", { name: "Insert" }));
    expect(body.value).toBe("First{{fx:10.3-11.1}} words");
  });

  it("inserts on Enter without saving the note", async () => {
    const form = await openEditor();
    const body = within(form).getByLabelText("Note") as HTMLTextAreaElement;
    body.setSelectionRange(0, 0);
    const place = within(form).getByLabelText("Page or lines");
    fireEvent.change(place, { target: { value: "12" } });
    const enter = fireEvent.keyDown(place, { key: "Enter" });
    expect(enter).toBe(false); // default prevented: the note's form is not submitted
    expect(body.value).toBe("{{fx:12}}First words");
    // The picker is not a form of its own, which inside the note's form would save the note.
    expect(form.querySelector("form")).toBeNull();
  });

  it("refuses something that is not a place", async () => {
    const form = await openEditor();
    fireEvent.change(within(form).getByLabelText("Page or lines"), { target: { value: "chapter two" } });
    expect((within(form).getByRole("button", { name: "Insert" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("inserts a reference to another note on the page, or to a figure", async () => {
    const form = await openEditor();
    const body = within(form).getByLabelText("Note") as HTMLTextAreaElement;
    body.setSelectionRange(11, 11);
    const other = within(form).getByLabelText("Another note");
    // The note being edited is not offered as its own target.
    expect(within(other).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Choose…",
      "Clarification, line 2: A second note",
    ]);
    fireEvent.change(other, { target: { value: "43" } });
    expect(body.value).toBe("First words{{note:43}}");

    body.setSelectionRange(0, 0);
    fireEvent.change(within(form).getByLabelText("A figure"), { target: { value: "place:harbor" } });
    expect(body.value).toBe("![The harbor](fig:harbor)First words{{note:43}}");
    body.setSelectionRange(body.value.length, body.value.length);
    fireEvent.change(within(form).getByLabelText("A figure"), { target: { value: "cite:harbor" } });
    expect(body.value.endsWith("{{note:43}}{{fig:harbor}}")).toBe(true);
  });
});
