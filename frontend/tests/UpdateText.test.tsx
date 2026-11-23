import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { CorpusUpdateReport } from "../src/api/client";
import { App } from "../src/App";
import { forgetPrefs, mockApi, renderWithQuery, setUrl, VERSION } from "./helpers";

beforeEach(forgetPrefs);
afterEach(cleanup);

const REPORT: CorpusUpdateReport = {
  up_to_date: false,
  changed_pages: [8, 9],
  new_pages: [13, 14, 15],
  changed_paragraphs: 2,
  new_paragraphs: 6,
  moved_passages: 4,
  reworded_passages: 1,
  reworded_pages: [8],
  lost_passages: 1,
  lost_pages: [9],
  problems: [],
};

function open(handlers: Parameters<typeof mockApi>[0]) {
  const fetchMock = mockApi({ "GET /api/versions/1": () => ({ body: VERSION }), ...handlers });
  setUrl("/v/1/update-text");
  renderWithQuery(<App />);
  return fetchMock;
}

function check(): void {
  fireEvent.change(screen.getByLabelText("Folder of page files"), {
    target: { value: "/books/pages" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Check the folder" }));
}

function posts(fetchMock: ReturnType<typeof mockApi>): string[] {
  return fetchMock.mock.calls
    .filter(([, init]) => init?.method === "POST")
    .map(([url]) => String(url));
}

describe("Update the text", () => {
  it("checks first and says what differs, by page, before anything is written", async () => {
    const fetchMock = open({
      "POST /api/versions/1/update/preview": () => ({ body: REPORT }),
    });
    check();
    const report = await screen.findByRole("region", { name: "What differs" });
    expect(report.textContent).toContain("Changes on pages 8, 9, in 2 paragraphs.");
    expect(report.textContent).toContain("3 new pages: 13 to 15.");
    expect(report.textContent).toContain("4 marked passages will be shifted");
    expect(report.textContent).toContain("1 marked passage will read differently");
    expect(report.textContent).toContain("1 marked passage will lose its words");
    expect(within(report).getAllByRole("link", { name: "8" })[0]?.getAttribute("href")).toBe(
      "/v/1/p/8",
    );
    expect(posts(fetchMock)).toEqual(["/api/versions/1/update/preview"]);
    expect(screen.getByRole("button", { name: "Update" })).toBeTruthy();
  });

  it("updates after the check and reports what was done", async () => {
    const fetchMock = open({
      "POST /api/versions/1/update/preview": () => ({ body: REPORT }),
      "POST /api/versions/1/update": () => ({ body: REPORT }),
    });
    check();
    fireEvent.click(await screen.findByRole("button", { name: "Update" }));
    expect((await screen.findByRole("status")).textContent).toContain("Updated.");
    expect(screen.getByRole("region", { name: "What differs" }).textContent).toContain(
      "Changed pages 8, 9",
    );
    expect(screen.queryByRole("button", { name: "Update" })).toBeNull();
    expect(posts(fetchMock)).toEqual(["/api/versions/1/update/preview", "/api/versions/1/update"]);
  });

  it("offers no update when the files match the stored text", async () => {
    open({
      "POST /api/versions/1/update/preview": () => ({
        body: {
          ...REPORT,
          up_to_date: true,
          changed_pages: [],
          new_pages: [],
          moved_passages: 0,
          reworded_passages: 0,
          lost_passages: 0,
        },
      }),
    });
    check();
    const report = await screen.findByRole("region", { name: "What differs" });
    expect(report.textContent).toContain("There is nothing to update.");
    expect(screen.queryByRole("button", { name: "Update" })).toBeNull();
  });

  it("explains files that no longer line up, and offers no update", async () => {
    open({
      "POST /api/versions/1/update/preview": () => ({
        status: 409,
        body: { detail: "The files no longer match the stored text paragraph for paragraph." },
      }),
    });
    check();
    expect((await screen.findByRole("alert")).textContent).toContain("no longer match");
    expect(screen.queryByRole("button", { name: "Update" })).toBeNull();
  });
});
