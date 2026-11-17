import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Category, PageText } from "../src/api/client";
import { App } from "../src/App";
import { PageView } from "../src/page/PageView";
import {
  forgetPrefs,
  line,
  mockServer,
  renderWithQuery,
  selectText,
  setUrl,
  shapeLine,
  TYPES,
  VERSION,
} from "./helpers";

beforeEach(forgetPrefs);
afterEach(cleanup);

const CATEGORIES: Category[] = [
  { id: 1, name: "places", color: "#5b8c85", sort: 10, is_time: false },
  { id: 5, name: "time", color: "#a86a7a", sort: 50, is_time: true },
];

describe("entity mentions on the page", () => {
  it("underlines a mention in its category's color, also where a note covers it", () => {
    const lines = [
      line("alpha beta gamma delta", {
        line_no: 1,
        highlights: [{ annotation_id: 9, type_id: 2, level: 1, start: 0, end: 10 }],
        mentions: [{ mention_id: 4, category_id: 1, start: 6, end: 16 }],
      }),
    ];
    const { container } = render(
      <PageView mode="text" page={7} measure={30} lines={lines} categoryColors={{ 1: "#5b8c85" }} />,
    );
    const pieces = [...container.querySelectorAll<HTMLElement>("#l1 span")].map((piece) => [
      piece.textContent,
      piece.className,
      piece.dataset.notes,
      piece.dataset.mentions,
    ]);
    expect(pieces).toEqual([
      ["alpha ", "hl", "9", undefined],
      ["beta", "hl mention", "9", "4"],
      [" gamma", "mention", undefined, "4"],
    ]);
    const tagged = container.querySelector<HTMLElement>(".mention");
    expect(tagged?.style.getPropertyValue("--mention-color")).toBe("#5b8c85");
    // The line still reads the same.
    expect(container.querySelector("#l1")?.textContent).toBe("alpha beta gamma delta");
  });

  it("marks a mention under the bar in blank mode, with no words", () => {
    const lines = [
      shapeLine(40, { line_no: 1, mentions: [{ mention_id: 4, category_id: 1, start: 10, end: 20 }] }),
    ];
    const { container } = render(
      <PageView mode="blank" page={7} measure={40} lines={lines} categoryColors={{ 1: "#5b8c85" }} />,
    );
    const mark = container.querySelector<HTMLElement>(".bar-mention");
    expect([mark?.style.left, mark?.style.width]).toEqual(["25%", "25%"]);
    expect(container.querySelector(".page-body")?.textContent).toBe("");
  });
});

function pageText(): PageText {
  return {
    version_id: 1,
    edit_seq: 0,
    page: 7,
    prev_page: null,
    next_page: 8,
    division: VERSION.divisions[0] ?? null,
    lines: [
      line("came into Low Harbor on the", {
        id: 101,
        segment_id: 10,
        line_no: 1,
        mentions: [{ mention_id: 4, category_id: 1, start: 10, end: 20 }],
      }),
      line("last tide of October, 1871", { id: 102, segment_id: 10, start_offset: 28, line_no: 2 }),
    ],
  };
}

function openPage(extra: Parameters<typeof mockServer>[0] = {}) {
  const server = mockServer({
    "GET /api/versions/1": () => ({ body: VERSION }),
    "GET /api/note-types": () => ({ body: TYPES }),
    "GET /api/entity-categories": () => ({ body: CATEGORIES }),
    "GET /api/versions/1/pages/7/text": () => ({ body: pageText() }),
    "GET /api/versions/1/pages/7/notes": () => ({ body: [] }),
    "GET /api/versions/1/entities": (request) => ({
      body:
        request.query.category_id === "1" && "low harbor".startsWith((request.query.starting ?? "").toLowerCase())
          ? [{ id: 10, category_id: 1, name: "Low Harbor", value: null, places: [{ page: 7, line_no: 1 }] }]
          : [],
    }),
    "GET /api/versions/1/chronology": () => ({
      body: [
        {
          mention_id: 1, page: 3, line_no: 1, kind: "absolute", at: "1871", offset: null,
          relative_to_label: null, label: "arrival", remark: "", date_iso: "1871", date_words: "1871",
          elapsed_iso: null, elapsed_words: null, problem: null, since: [],
        },
      ],
    }),
    "POST /api/versions/1/mentions": () => ({ status: 201, body: { id: 77 } }),
    ...extra,
  });
  setUrl("/v/1/p/7");
  renderWithQuery(<App />);
  return server;
}

function rowText(page: HTMLElement, lineNo: number, index = 0): Text {
  const row = page.querySelector(`#l${lineNo}`) as HTMLElement;
  const walker = document.createTreeWalker(row, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text);
  return nodes[index] as Text;
}

describe("tagging entities", () => {
  it("shows mentions underlined, and hides them with the toggle, remembered", async () => {
    openPage();
    const page = await screen.findByLabelText("Page 7");
    await waitFor(() => expect(page.querySelector(".mention")?.textContent).toBe("Low Harbor"));
    fireEvent.click(screen.getByLabelText("Underline entities"));
    expect(page.querySelector(".mention")).toBeNull();
    expect(page.querySelector("#l1")?.textContent).toBe("came into Low Harbor on the");
    expect(JSON.parse(window.localStorage.getItem("pneutext.prefs") ?? "{}")).toMatchObject({
      showMentions: false,
    });
  });

  it("assigns the selection to an existing entity found by type-ahead", async () => {
    const { sent } = openPage();
    const page = await screen.findByLabelText("Page 7");
    await waitFor(() => expect(page.querySelector(".mention")).not.toBeNull());
    const words = rowText(page, 1, 1); // the "Low Harbor" piece
    selectText(words, 0, words, 10);
    const popover = await screen.findByRole("dialog", { name: "Selection" });
    fireEvent.click(within(popover).getByRole("button", { name: "Tag entity" }));

    const form = within(popover).getByRole("form", { name: "Tag entity" });
    // The words selected name the entity unless another name is typed.
    expect(within(form).getByLabelText("Entity")).toHaveProperty("value", "Low Harbor");
    await waitFor(() => expect(form.querySelector("datalist option")?.getAttribute("value")).toBe("Low Harbor"));
    fireEvent.click(within(form).getByRole("button", { name: "Tag" }));

    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toEqual({
      category_id: 1,
      entity_id: 10,
      entity_name: null,
      value: null,
      span: { start_segment_id: 10, start_offset: 10, end_segment_id: 10, end_offset: 20, exact: "Low Harbor" },
    });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Selection" })).toBeNull());
  });

  it("makes a new entity with a normalized value, opened with the e key", async () => {
    const { sent } = openPage();
    const page = await screen.findByLabelText("Page 7");
    await screen.findByText("last tide of October, 1871");
    selectText(rowText(page, 2), 22, rowText(page, 2), 26);
    await screen.findByRole("dialog", { name: "Selection" });
    fireEvent.keyDown(window, { key: "e" });
    const form = await screen.findByRole("form", { name: "Tag entity" });
    fireEvent.change(within(form).getByLabelText("Entity"), { target: { value: "the year" } });
    fireEvent.change(within(form).getByLabelText("Value"), { target: { value: "1871" } });
    fireEvent.click(within(form).getByRole("button", { name: "Tag" }));
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toMatchObject({
      category_id: 1,
      entity_id: null,
      entity_name: "the year",
      value: "1871",
      span: { exact: "1871", start_offset: 50, end_offset: 54 },
    });
  });

  it("tags a time with a date, or an offset from a labeled time", async () => {
    const { sent } = openPage();
    const page = await screen.findByLabelText("Page 7");
    await screen.findByText("last tide of October, 1871");
    selectText(rowText(page, 2), 13, rowText(page, 2), 26);
    fireEvent.click(await screen.findByRole("button", { name: "Tag entity" }));
    const form = await screen.findByRole("form", { name: "Tag entity" });
    fireEvent.change(within(form).getByLabelText("Category"), { target: { value: "5" } });
    // A time has no entity: the form asks for a time instead.
    expect(within(form).queryByLabelText("Entity")).toBeNull();
    fireEvent.change(within(form).getByLabelText("Kind"), { target: { value: "offset" } });
    fireEvent.change(within(form).getByLabelText("Offset"), { target: { value: "P5D" } });
    fireEvent.change(within(form).getByLabelText("Counts from"), { target: { value: "arrival" } });
    fireEvent.click(within(form).getByRole("button", { name: "Tag" }));
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toMatchObject({
      category_id: 5,
      time: { kind: "offset", at: null, offset: "P5D", relative_to_label: "arrival", label: null, remark: "" },
      span: { exact: "October, 1871" },
    });
  });

  it("can tag a time now and give its value later", async () => {
    const { sent } = openPage();
    const page = await screen.findByLabelText("Page 7");
    await screen.findByText("last tide of October, 1871");
    selectText(rowText(page, 2), 13, rowText(page, 2), 26);
    fireEvent.click(await screen.findByRole("button", { name: "Tag entity" }));
    const form = await screen.findByRole("form", { name: "Tag entity" });
    fireEvent.change(within(form).getByLabelText("Category"), { target: { value: "5" } });
    fireEvent.click(within(form).getByRole("button", { name: "Tag" }));
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toMatchObject({ category_id: 5, time: null });
  });

  it("keeps the form open and explains when the server refuses", async () => {
    openPage({
      "POST /api/versions/1/mentions": () => ({
        status: 400,
        body: { detail: "Write the date as a year, a month, a day or a time." },
      }),
    });
    const page = await screen.findByLabelText("Page 7");
    await screen.findByText("last tide of October, 1871");
    selectText(rowText(page, 2), 13, rowText(page, 2), 26);
    fireEvent.click(await screen.findByRole("button", { name: "Tag entity" }));
    const form = await screen.findByRole("form", { name: "Tag entity" });
    fireEvent.click(within(form).getByRole("button", { name: "Tag" }));
    expect((await within(form).findByRole("alert")).textContent).toContain("Write the date");
    fireEvent.click(within(form).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "Tag entity" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "Selection" })).toBeTruthy();
  });
});
