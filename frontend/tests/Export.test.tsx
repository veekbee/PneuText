import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { MonographResult, Profile } from "../src/api/client";
import { App } from "../src/App";
import { forgetPrefs, mockServer, renderWithQuery, setUrl, TYPES, VERSION } from "./helpers";

beforeEach(forgetPrefs);
afterEach(cleanup);

const PROFILES: Profile[] = [
  { id: 1, name: "First reading", type_ids: null, levels: [1], statuses: ["ready"] },
  { id: 2, name: "Full edition", type_ids: [1, 2], levels: [1, 2], statuses: ["ready"] },
];

const RESULT: MonographResult = {
  folder: "/library/exports/fx-first-reading",
  files: ["chapters/chapter-01.tex", "main.tex", "pneutext.sty"],
  notes: 12,
  pages: 4,
  pdf: null,
  build: "No LaTeX is installed, so only the source was written.",
  warnings: ["The figure chain has no image; a placeholder is printed."],
};

function open(extra: Parameters<typeof mockServer>[0] = {}, builder: string | null = null) {
  const server = mockServer({
    "GET /api/versions/1": () => ({ body: VERSION }),
    "GET /api/note-types": () => ({ body: TYPES }),
    "GET /api/export-profiles": () => ({ body: PROFILES }),
    "GET /api/versions/1/exports/monograph/defaults": (request) => ({
      body: { folder: `/library/exports/fx-${request.query.profile_id}`, pdf_builder: builder },
    }),
    "POST /api/versions/1/exports/monograph": () => ({ body: RESULT }),
    "POST /api/exports/backup": (request) => ({
      body: {
        folder: "/library/exports/backup",
        files: ["library.json"],
        includes_text: (request.body as { include_text: boolean }).include_text,
      },
    }),
    ...extra,
  });
  setUrl("/v/1/export");
  renderWithQuery(<App />);
  return server;
}

describe("exporting the monograph", () => {
  it("exports the chosen edition and reports what was written", async () => {
    const { sent } = open();
    const edition = await screen.findByLabelText("Edition");
    expect(screen.getByText("Includes every note type; first-reading notes only; ready notes only.")).toBeTruthy();
    fireEvent.change(edition, { target: { value: "2" } });
    expect(screen.getByText("Includes Clarification, Comment; every reading level; ready notes only.")).toBeTruthy();
    // Where it will be written, and that no PDF can be built here.
    await waitFor(() =>
      expect(screen.getAllByLabelText("Folder to write to")[0]?.getAttribute("placeholder")).toBe(
        "/library/exports/fx-2",
      ),
    );
    expect(screen.getByText(/no LaTeX is installed here/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Export the monograph" }));
    const result = await screen.findByRole("status", { name: "Export result" });
    expect(result.textContent).toContain("Wrote 3 files to /library/exports/fx-first-reading: 12 notes on 4 pages.");
    expect(result.textContent).toContain("No LaTeX is installed, so only the source was written.");
    expect(within(result).getByText("The figure chain has no image; a placeholder is printed.")).toBeTruthy();
    expect(sent.map((request) => [request.path, request.body])).toEqual([
      ["/api/versions/1/exports/monograph", { profile_id: 2, folder: null, build_pdf: true }],
    ]);
  });

  it("says which program will build the PDF, and can write to a folder of the author's choosing", async () => {
    const { sent } = open(
      { "POST /api/versions/1/exports/monograph": () => ({ body: { ...RESULT, pdf: "/out/main.pdf", build: "Built with latexmk." } }) },
      "latexmk",
    );
    await screen.findByText(/with latexmk/);
    fireEvent.change(screen.getAllByLabelText("Folder to write to")[0] as HTMLElement, { target: { value: "/out" } });
    fireEvent.click(screen.getByLabelText(/Build the PDF as well/));
    fireEvent.click(screen.getByRole("button", { name: "Export the monograph" }));
    expect((await screen.findByRole("status", { name: "Export result" })).textContent).toContain("PDF: /out/main.pdf");
    expect(sent[0]?.body).toEqual({ profile_id: 1, folder: "/out", build_pdf: false });
  });

  it("shows the server's explanation when the export fails", async () => {
    open({
      "POST /api/versions/1/exports/monograph": () => ({
        status: 400,
        body: { detail: "/out/file.txt is a file, not a folder." },
      }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Export the monograph" }));
    expect((await screen.findByRole("alert")).textContent).toContain("is a file, not a folder");
  });
});

describe("editions", () => {
  it("saves a new edition choosing types, levels and statuses", async () => {
    const { sent } = open({
      "POST /api/export-profiles": () => ({
        status: 201,
        body: { id: 3, name: "Spanish", type_ids: [2], levels: [1, 2], statuses: ["draft", "ready"] },
      }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "New edition" }));
    const form = screen.getByRole("form", { name: "New edition" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Spanish" } });
    fireEvent.click(within(form).getByLabelText(/know the whole book/));
    fireEvent.click(within(form).getByLabelText(/Include drafts/));
    fireEvent.click(within(form).getByLabelText("Clarification"));
    fireEvent.click(within(form).getByLabelText("Chapter summary"));
    fireEvent.click(within(form).getByRole("button", { name: "Add edition" }));
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toEqual({
      name: "Spanish",
      type_ids: [2],
      levels: [1, 2],
      statuses: ["draft", "ready"],
    });
  });

  it("changes and deletes an existing edition", async () => {
    const { sent } = open({
      "PUT /api/export-profiles/1": () => ({ body: PROFILES[0] }),
      "DELETE /api/export-profiles/1": () => ({ status: 204, body: null }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Change this edition" }));
    const form = screen.getByRole("form", { name: "Edit First reading" });
    // Every type chosen is stored as "all", so types added later are included too.
    fireEvent.click(within(form).getByLabelText(/know the whole book/));
    fireEvent.click(within(form).getByRole("button", { name: "Save edition" }));
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toEqual({ name: "First reading", type_ids: null, levels: [1, 2], statuses: ["ready"] });

    fireEvent.click(await screen.findByRole("button", { name: "Change this edition" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete edition" }));
    await waitFor(() => expect(sent.map((request) => request.method)).toEqual(["PUT", "DELETE"]));
  });
});

describe("backups", () => {
  it("backs up without the text by default, or everything, and says which", async () => {
    const { sent } = open();
    fireEvent.click(await screen.findByRole("button", { name: "Back up without the text" }));
    const first = await screen.findByRole("status", { name: "Backup result" });
    expect(first.textContent).toContain("contains no text of the book");
    fireEvent.click(screen.getByRole("button", { name: /Back up everything/ }));
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "Backup result" }).textContent).toContain("Keep it private"),
    );
    expect(sent.map((request) => request.body)).toEqual([
      { folder: null, include_text: false },
      { folder: null, include_text: true },
    ]);
  });
});
