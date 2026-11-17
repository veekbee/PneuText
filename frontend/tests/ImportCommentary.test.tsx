import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { LegacyReport } from "../src/api/client";
import { App } from "../src/App";
import { forgetPrefs, mockApi, renderWithQuery, setUrl, VERSION } from "./helpers";

beforeEach(forgetPrefs);
afterEach(cleanup);

const REPORT: LegacyReport = {
  files: 5,
  pages: [8, 9],
  notes: 13,
  flagged_notes: 3,
  chapter_notes: 2,
  remarks: 1,
  mentions: 16,
  new_categories: ["weather"],
  new_types: ["Theme"],
  figures: 2,
  replaced_notes: 0,
  replaced_mentions: 0,
  groups: [
    {
      code: "span_without_note",
      title: "Spans without a note",
      items: [
        {
          code: "span_without_note",
          page: 8,
          line: 13,
          tag: "{c_p8_marsh}",
          message: "Page 8, line 13: {c_p8_marsh} has no note block; it was imported as a flagged highlight.",
        },
      ],
    },
  ],
  repairs: [
    {
      code: "category_name",
      page: 8,
      line: 8,
      tag: "|times|",
      message: "Page 8, line 8: |times| was read as the category time.",
    },
  ],
};

function open(handlers: Parameters<typeof mockApi>[0]) {
  const sent: unknown[] = [];
  const fetchMock = mockApi({
    "GET /api/versions/1": () => ({ body: VERSION }),
    ...Object.fromEntries(
      Object.entries(handlers).map(([key, handler]) => [
        key,
        (body: unknown) => {
          sent.push(body);
          return handler(body);
        },
      ]),
    ),
  });
  setUrl("/v/1/import-commentary");
  renderWithQuery(<App />);
  return { sent, fetchMock };
}

function check(folder = "/books/commentary"): void {
  fireEvent.change(screen.getByLabelText("Folder of commentary files"), {
    target: { value: folder },
  });
  fireEvent.click(screen.getByRole("button", { name: "Check the folder" }));
}

describe("Import old commentary", () => {
  it("runs a dry run first and shows the report grouped by problem, with repairs", async () => {
    const { sent, fetchMock } = open({
      "POST /api/versions/1/imports/commentary/preview": () => ({ body: REPORT }),
    });
    fireEvent.change(screen.getByLabelText(/LaTeX commands that cite a page of this text/), {
      target: { value: "pref, \\cite " },
    });
    check();

    const report = await screen.findByRole("region", { name: "What was found" });
    expect(within(report).getByText("13")).toBeTruthy();
    const group = within(report).getByRole("region", { name: "Spans without a note" });
    expect(within(group).getByText(/\{c_p8_marsh\} has no note block/)).toBeTruthy();
    const repairs = within(report).getByRole("region", { name: "Repairs" });
    expect(within(repairs).getByText(/\|times\| was read as the category time/)).toBeTruthy();
    expect(within(report).getByText("New category: weather.")).toBeTruthy();
    expect(within(report).getByText("New note type: Theme.")).toBeTruthy();

    expect(sent).toEqual([
      {
        folder: "/books/commentary",
        file_pattern: null,
        page_ref_commands: ["pref", "\\cite"],
        figures_folder: null,
      },
    ]);
    // Nothing has been imported yet: only the preview was asked for.
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts.map(([url]) => String(url))).toEqual(["/api/versions/1/imports/commentary/preview"]);
    expect(screen.getByRole("button", { name: "Import" })).toBeTruthy();
  });

  it("imports after the dry run and offers the first imported page", async () => {
    open({
      "POST /api/versions/1/imports/commentary/preview": () => ({ body: REPORT }),
      "POST /api/versions/1/imports/commentary": () => ({ status: 201, body: REPORT }),
    });
    check();
    fireEvent.click(await screen.findByRole("button", { name: "Import" }));
    const done = await screen.findByRole("status");
    expect(done.textContent).toContain("Imported.");
    expect(within(done).getByRole("link", { name: "Open page 8" }).getAttribute("href")).toBe(
      "/v/1/p/8",
    );
    expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
    expect(screen.getByRole("region", { name: "What was found" })).toBeTruthy();
  });

  it("warns what a second import replaces", async () => {
    open({
      "POST /api/versions/1/imports/commentary/preview": () => ({
        body: { ...REPORT, replaced_notes: 16, replaced_mentions: 1 },
      }),
    });
    check();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("replaces 16 notes and 1 mention");
    expect(alert.textContent).toContain("Notes made in the app are kept");
  });

  it("explains a folder that cannot be read, and offers no import", async () => {
    open({
      "POST /api/versions/1/imports/commentary/preview": () => ({
        status: 400,
        body: { detail: "There is no folder at /books/commentary." },
      }),
    });
    check();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("There is no folder at /books/commentary.");
    expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
  });

  it("drops a stale report when an answer changes", async () => {
    open({ "POST /api/versions/1/imports/commentary/preview": () => ({ body: REPORT }) });
    check();
    await screen.findByRole("region", { name: "What was found" });
    fireEvent.change(screen.getByLabelText("Folder of commentary files"), {
      target: { value: "/books/other" },
    });
    expect(screen.queryByRole("region", { name: "What was found" })).toBeNull();
  });
});
