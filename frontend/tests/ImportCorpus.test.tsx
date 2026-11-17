import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { App } from "../src/App";
import { forgetPrefs, mockApi, pageOf, renderWithQuery, setUrl, VERSION } from "./helpers";

beforeEach(forgetPrefs);
afterEach(cleanup);

const SUMMARY = { pages: 3, lines: 40, paragraphs: 6, chapters: 2, first_page: 7, last_page: 9 };

function fillForm(): void {
  fireEvent.change(screen.getByLabelText("Folder of page files"), {
    target: { value: "/books/fixture" },
  });
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "The Fixture Book" } });
  fireEvent.change(screen.getByLabelText(/^Short code/), { target: { value: "fx" } });
}

describe("Import a corpus", () => {
  it("checks the folder, shows the summary and warnings, then imports and opens the book", async () => {
    const sent: unknown[] = [];
    mockApi({
      "POST /api/imports/corpus/preview": (body) => {
        sent.push(body);
        return {
          body: {
            summary: SUMMARY,
            problems: [
              {
                code: "unknown_directive",
                page: 8,
                line: 3,
                message: "Page 8, line 3: unknown directive <<mystery>>; it was left out of the text.",
              },
            ],
            existing_version_id: null,
          },
        };
      },
      "POST /api/imports/corpus": (body) => {
        sent.push(body);
        return {
          status: 201,
          body: { version_id: 1, summary: SUMMARY, problems: [], existing_version_id: null },
        };
      },
      "GET /api/versions/1": () => ({ body: VERSION }),
      "GET /api/versions/1/pages/7/text": () => ({ body: pageOf(7, "seventh page words") }),
    });
    setUrl("/import");
    renderWithQuery(<App />);
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Check the folder" }));

    expect(await screen.findByRole("heading", { name: "What was found" })).toBeTruthy();
    expect(screen.getByText("40")).toBeTruthy();
    expect(screen.getByText(/unknown directive <<mystery>>/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText("seventh page words")).toBeTruthy();
    expect(window.location.pathname).toBe("/v/1/p/7");
    expect(sent).toEqual([
      expect.objectContaining({ folder: "/books/fixture", work_code: "fx", allow_duplicate: false }),
      expect.objectContaining({ folder: "/books/fixture", work_code: "fx", allow_duplicate: false }),
    ]);
  });

  it("warns when the files were imported before and offers the existing version", async () => {
    const sent: unknown[] = [];
    mockApi({
      "POST /api/imports/corpus/preview": () => ({
        body: { summary: SUMMARY, problems: [], existing_version_id: 4 },
      }),
      "POST /api/imports/corpus": (body) => {
        sent.push(body);
        return {
          status: 201,
          body: { version_id: 5, summary: SUMMARY, problems: [], existing_version_id: 4 },
        };
      },
    });
    setUrl("/import");
    renderWithQuery(<App />);
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Check the folder" }));

    const existing = await screen.findByRole("link", { name: "Open the existing version" });
    expect(existing.getAttribute("href")).toBe("/v/4/p/7");
    fireEvent.click(screen.getByRole("button", { name: "Import a second copy" }));
    await screen.findByText(/Opening the page|no test handler/i);
    expect(sent).toEqual([expect.objectContaining({ allow_duplicate: true })]);
  });

  it("explains a folder that cannot be read", async () => {
    mockApi({
      "POST /api/imports/corpus/preview": () => ({
        status: 400,
        body: { detail: "There is no folder at /books/fixture." },
      }),
    });
    setUrl("/import");
    renderWithQuery(<App />);
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Check the folder" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("There is no folder at /books/fixture.");
    expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
  });

  it("drops a stale summary when an answer changes", async () => {
    mockApi({
      "POST /api/imports/corpus/preview": () => ({
        body: { summary: SUMMARY, problems: [], existing_version_id: null },
      }),
    });
    setUrl("/import");
    renderWithQuery(<App />);
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Check the folder" }));
    await screen.findByRole("heading", { name: "What was found" });
    fireEvent.change(screen.getByLabelText("Folder of page files"), {
      target: { value: "/books/other" },
    });
    expect(screen.queryByRole("heading", { name: "What was found" })).toBeNull();
  });
});
