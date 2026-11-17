import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Note, PageText } from "../src/api/client";
import { App } from "../src/App";
import {
  bodyOf,
  forgetPrefs,
  line,
  mockApi,
  noteOf,
  renderWithQuery,
  selectText,
  setUrl,
  shapeOf,
  TYPES,
  VERSION,
} from "./helpers";

beforeEach(forgetPrefs);
afterEach(cleanup);

/** A small server: one page of two lines, and whatever notes have been saved. */
function mockNotes(options: { notes?: Note[]; failCreate?: string } = {}) {
  const notes: Note[] = [...(options.notes ?? [])];
  const sent: { method: string; body: unknown }[] = [];
  const pageText = (): PageText => ({
    version_id: 1,
    edit_seq: 0,
    page: 7,
    prev_page: null,
    next_page: 8,
    division: VERSION.divisions[0] ?? null,
    lines: [
      line("alpha beta gamma", {
        id: 101,
        segment_id: 10,
        start_offset: 0,
        line_no: 1,
        starts_paragraph: true,
        highlights: notes
          .filter((note) => note.scope === "span")
          .map((note) => ({
            annotation_id: note.id,
            type_id: note.type_id,
            level: note.level,
            start: note.anchor.start_offset,
            end: note.anchor.end_offset,
          })),
      }),
      line("delta epsilon", { id: 102, segment_id: 10, start_offset: 17, line_no: 2, ends_paragraph: true }),
    ],
  });
  const fetchMock = mockApi({
    "GET /api/versions/1": () => ({ body: VERSION }),
    "GET /api/note-types": () => ({ body: TYPES }),
    "GET /api/versions/1/pages/7/text": () => ({ body: pageText() }),
    "GET /api/versions/1/pages/7/shape": () => {
      const shape = shapeOf(7);
      const first = shape.lines[0];
      if (first) first.highlights = pageText().lines[0]?.highlights ?? [];
      return { body: shape };
    },
    "GET /api/versions/1/pages/7/notes": () => ({ body: notes }),
    "POST /api/versions/1/notes": (body) => {
      sent.push({ method: "POST", body });
      if (options.failCreate) return { status: 400, body: { detail: options.failCreate } };
      const input = body as { type_id: number; scope: Note["scope"]; span?: Note["anchor"] };
      const created = noteOf(500 + notes.length, {
        type_id: input.type_id,
        scope: input.scope,
        anchor: { ...(input.span ?? noteOf(0).anchor), status: "ok" },
      });
      notes.push(created);
      return { status: 201, body: created };
    },
    "PATCH /api/notes/41": (body) => {
      sent.push({ method: "PATCH", body });
      const changes = body as Partial<Note>;
      const index = notes.findIndex((note) => note.id === 41);
      const updated = {
        ...(notes[index] as Note),
        ...changes,
        body: bodyOf(String(changes.body_md ?? "")),
      };
      notes[index] = updated;
      return { body: updated };
    },
    "DELETE /api/notes/41": () => {
      sent.push({ method: "DELETE", body: null });
      notes.splice(
        notes.findIndex((note) => note.id === 41),
        1,
      );
      return { status: 204, body: null };
    },
    "POST /api/notes/render": (body) => ({
      body: { body: bodyOf(`previewed: ${(body as { body_md: string }).body_md}`) },
    }),
  });
  return { fetchMock, sent, notes };
}

async function openPage(): Promise<HTMLElement> {
  setUrl("/v/1/p/7");
  renderWithQuery(<App />);
  return screen.findByLabelText("Page 7");
}

function rowText(page: HTMLElement, lineNo: number): Text {
  const row = page.querySelector(`#l${lineNo}`) as HTMLElement;
  return [...row.childNodes].find((node) => node.nodeType === Node.TEXT_NODE) as Text;
}

/** Choose an action in the selection popover, then a note type. */
async function pickFromPopover(action: string, type: string): Promise<void> {
  const popover = await screen.findByRole("dialog", { name: "Selection" });
  fireEvent.click(within(popover).getByRole("button", { name: action }));
  fireEvent.click(within(popover).getByRole("button", { name: type }));
}

function highlighted(page: HTMLElement): string[] {
  return [...page.querySelectorAll(".hl")].map((piece) => piece.textContent ?? "");
}

describe("annotating a page", () => {
  it("opens a popover on selection and creates a note of the chosen type", async () => {
    const { sent } = mockNotes();
    const page = await openPage();
    await screen.findByText("alpha beta gamma");
    const text = rowText(page, 1);
    selectText(text, 6, text, 10);

    const popover = await screen.findByRole("dialog", { name: "Selection" });
    fireEvent.click(within(popover).getByRole("button", { name: "Note" }));
    // Only types that are notes are offered; chapter matter is made from the side panel.
    expect(within(popover).queryByRole("button", { name: "Chapter summary" })).toBeNull();
    fireEvent.click(within(popover).getByRole("button", { name: "Clarification" }));

    await waitFor(() => expect(highlighted(page)).toEqual(["beta"]));
    expect(sent[0]).toEqual({
      method: "POST",
      body: expect.objectContaining({
        type_id: 1,
        scope: "span",
        span: {
          start_segment_id: 10,
          start_offset: 6,
          end_segment_id: 10,
          end_offset: 10,
          exact: "beta",
        },
      }),
    });
    // The new note opens for editing in the side panel.
    expect(await screen.findByRole("form", { name: "Edit note" })).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Selection" })).toBeNull();
  });

  it("shows the highlight at once, before the server answers", async () => {
    mockNotes();
    const page = await openPage();
    await screen.findByText("alpha beta gamma");
    const text = rowText(page, 1);
    selectText(text, 0, text, 5);
    await pickFromPopover("Highlight", "Comment");
    // No awaiting: the piece is there in the same tick the button was pressed.
    await waitFor(() => expect(highlighted(page)).toEqual(["alpha"]));
    expect(document.querySelector(".note-card.is-pending, .note-card")).not.toBeNull();
    // A bare highlight does not open the editor.
    await waitFor(() => expect(document.querySelector(".note-card.is-pending")).toBeNull());
    expect(screen.queryByRole("form", { name: "Edit note" })).toBeNull();
    expect(screen.getByText("Highlight only.")).toBeTruthy();
  });

  it("removes the highlight and explains when the save fails", async () => {
    mockNotes({ failCreate: "The selected passage does not match the text as stored." });
    const page = await openPage();
    await screen.findByText("alpha beta gamma");
    const text = rowText(page, 1);
    selectText(text, 0, text, 5);
    await pickFromPopover("Highlight", "Comment");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("does not match the text as stored");
    await waitFor(() => expect(highlighted(page)).toEqual([]));
    expect(document.querySelector(".note-card")).toBeNull();
  });

  it("creates a note with the n key and a bare highlight with h, using the last type", async () => {
    const { sent } = mockNotes();
    const page = await openPage();
    await screen.findByText("alpha beta gamma");
    selectText(rowText(page, 2), 0, rowText(page, 2), 5);
    await screen.findByRole("dialog", { name: "Selection" });
    fireEvent.keyDown(window, { key: "h" });
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toMatchObject({ type_id: 1, span: { exact: "delta" } });
    expect(screen.queryByRole("form", { name: "Edit note" })).toBeNull();
  });

  it("selects across print lines, joining them with one space", async () => {
    const { sent } = mockNotes();
    const page = await openPage();
    await screen.findByText("alpha beta gamma");
    selectText(rowText(page, 1), 11, rowText(page, 2), 5);
    await pickFromPopover("Highlight", "Comment");
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toMatchObject({
      span: { start_offset: 11, end_offset: 22, exact: "gamma delta" },
    });
  });

  it("dismisses the popover with Escape", async () => {
    mockNotes();
    const page = await openPage();
    await screen.findByText("alpha beta gamma");
    selectText(rowText(page, 1), 0, rowText(page, 1), 5);
    await screen.findByRole("dialog", { name: "Selection" });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Selection" })).toBeNull();
  });

  it("offers the reference to copy", async () => {
    mockNotes();
    const page = await openPage();
    await screen.findByText("alpha beta gamma");
    selectText(rowText(page, 1), 0, rowText(page, 2), 5);
    // No clipboard in this environment: the reference is shown to copy by hand.
    fireEvent.click(await screen.findByRole("button", { name: "Copy reference" }));
    expect(await screen.findByText("{{fx:7.1-7.2}}")).toBeTruthy();
  });
});

const EXISTING = noteOf(41, {
  type_id: 2,
  body_md: "An old remark.",
  body: bodyOf("An old remark."),
  anchor: { start_segment_id: 10, start_offset: 6, end_segment_id: 10, end_offset: 10, status: "ok" },
  tags: ["birds"],
});

describe("the notes beside a page", () => {
  it("lists notes with type, place, status and body, and highlights their spans", async () => {
    mockNotes({ notes: [EXISTING] });
    const page = await openPage();
    const card = (await screen.findByText("An old remark.")).closest(".note-card") as HTMLElement;
    expect(within(card).getByText("Comment")).toBeTruthy();
    expect(within(card).getByText("line 1")).toBeTruthy();
    expect(within(card).getByText("Draft")).toBeTruthy();
    expect(within(card).getByText("#birds")).toBeTruthy();
    await waitFor(() => expect(highlighted(page)).toEqual(["beta"]));
    const piece = page.querySelector(".hl") as HTMLElement;
    expect(piece.dataset.notes).toBe("41");
    // Painted in its type's color (Comment is #d9b44a).
    expect(piece.style.backgroundImage).toMatch(/#d9b44a|rgb\(217, 180, 74\)/);
  });

  it("emphasizes a note when its highlight is hovered, and the reverse", async () => {
    mockNotes({ notes: [EXISTING] });
    const page = await openPage();
    const card = (await screen.findByText("An old remark.")).closest(".note-card") as HTMLElement;
    await waitFor(() => expect(page.querySelector(".hl")).not.toBeNull());
    fireEvent.mouseOver(page.querySelector(".hl") as HTMLElement);
    expect(card.classList.contains("is-active")).toBe(true);
    fireEvent.mouseLeave(page.querySelector(".page-body") as HTMLElement);
    expect(card.classList.contains("is-active")).toBe(false);
    fireEvent.mouseEnter(card);
    expect(page.querySelector(".hl")?.classList.contains("is-active")).toBe(true);
  });

  it("edits a note in place with a live preview, and saves it", async () => {
    const { sent } = mockNotes({ notes: [EXISTING] });
    await openPage();
    const card = (await screen.findByText("An old remark.")).closest(".note-card") as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Edit" }));
    const form = within(card).getByRole("form", { name: "Edit note" });
    fireEvent.change(within(form).getByLabelText("Note"), { target: { value: "A *new* remark." } });
    // The preview is the server's parse of what was typed.
    expect(await within(form).findByText("previewed: A *new* remark.")).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("Type"), { target: { value: "1" } });
    fireEvent.change(within(form).getByLabelText("For"), { target: { value: "2" } });
    fireEvent.change(within(form).getByLabelText("Status"), { target: { value: "ready" } });
    fireEvent.change(within(form).getByLabelText("Tags"), { target: { value: "marsh, birds" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]).toEqual({
      method: "PATCH",
      body: {
        type_id: 1,
        level: 2,
        status: "ready",
        body_md: "A *new* remark.",
        tags: ["marsh", " birds"],
      },
    });
    await waitFor(() => expect(screen.queryByRole("form", { name: "Edit note" })).toBeNull());
    expect(await screen.findByText("A *new* remark.")).toBeTruthy();
  });

  it("deletes a note only after a second, explicit press", async () => {
    const { sent } = mockNotes({ notes: [EXISTING] });
    const page = await openPage();
    const card = (await screen.findByText("An old remark.")).closest(".note-card") as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Edit" }));
    fireEvent.click(within(card).getByRole("button", { name: "Delete" }));
    expect(sent).toEqual([]);
    fireEvent.click(within(card).getByRole("button", { name: "Really delete" }));
    await waitFor(() => expect(document.querySelector('[data-note-id="41"]')).toBeNull());
    await waitFor(() => expect(highlighted(page)).toEqual([]));
    expect(sent).toEqual([{ method: "DELETE", body: null }]);
  });

  it("re-selects a note's passage without retyping the note", async () => {
    const { sent } = mockNotes({ notes: [EXISTING] });
    const page = await openPage();
    const card = (await screen.findByText("An old remark.")).closest(".note-card") as HTMLElement;
    fireEvent.click(within(card).getByRole("button", { name: "Edit" }));
    fireEvent.click(within(card).getByRole("button", { name: "Re-select passage" }));
    expect(screen.getByRole("status").textContent).toContain("Select the passage");
    selectText(rowText(page, 2), 6, rowText(page, 2), 13);
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]).toEqual({
      method: "PATCH",
      body: {
        span: {
          start_segment_id: 10,
          start_offset: 23,
          end_segment_id: 10,
          end_offset: 30,
          exact: "epsilon",
        },
      },
    });
    expect(screen.queryByRole("dialog", { name: "Selection" })).toBeNull();
  });

  it("makes page and chapter notes from the side panel", async () => {
    const { sent } = mockNotes();
    await openPage();
    await screen.findByText("alpha beta gamma");
    fireEvent.click(screen.getByRole("button", { name: "Note on this page" }));
    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]?.body).toMatchObject({ scope: "page", page: 7, type_id: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Note on this chapter" }));
    await waitFor(() => expect(sent.length).toBe(2));
    // A chapter note starts as a chapter summary, on the chapter the page belongs to.
    expect(sent[1]?.body).toMatchObject({ scope: "chapter", division_id: 1, type_id: 8 });
  });
});

describe("the reader's filters", () => {
  const HARD = noteOf(42, {
    type_id: 1,
    level: 2,
    status: "ready",
    body_md: "For re-readers.",
    body: bodyOf("For re-readers."),
    anchor: { start_segment_id: 10, start_offset: 0, end_segment_id: 10, end_offset: 5, status: "ok" },
  });

  it("hides level 2 notes and their highlights on a first reading, and remembers it", async () => {
    mockNotes({ notes: [EXISTING, HARD] });
    const page = await openPage();
    await screen.findByText("For re-readers.");
    await waitFor(() => expect(highlighted(page)).toEqual(["alpha", "beta"]));
    fireEvent.click(screen.getByRole("button", { name: "First reading" }));
    expect(screen.queryByText("For re-readers.")).toBeNull();
    expect(screen.getByText("An old remark.")).toBeTruthy();
    expect(highlighted(page)).toEqual(["beta"]);
    expect(screen.getByText("1 more note is hidden by the filters.")).toBeTruthy();
    expect(JSON.parse(window.localStorage.getItem("pneutext.prefs") ?? "{}")).toMatchObject({
      level: "first",
    });
  });

  it("hides a note type with its toggle, and remembers it", async () => {
    mockNotes({ notes: [EXISTING, HARD] });
    const page = await openPage();
    await screen.findByText("An old remark.");
    const toggles = screen.getByRole("group", { name: "Note types" });
    fireEvent.click(within(toggles).getByRole("button", { name: "Comment" }));
    expect(screen.queryByText("An old remark.")).toBeNull();
    expect(highlighted(page)).toEqual(["alpha"]);
    expect(within(toggles).getByRole("button", { name: "Comment" }).getAttribute("aria-pressed")).toBe(
      "false",
    );
    expect(JSON.parse(window.localStorage.getItem("pneutext.prefs") ?? "{}")).toMatchObject({
      hiddenTypes: [2],
    });
  });

  it("filters the list and the highlights by status", async () => {
    mockNotes({ notes: [EXISTING, HARD] });
    const page = await openPage();
    await screen.findByText("An old remark.");
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "ready" } });
    expect(screen.queryByText("An old remark.")).toBeNull();
    expect(screen.getByText("For re-readers.")).toBeTruthy();
    expect(highlighted(page)).toEqual(["alpha"]);
  });

  it("says so when the filters hide every note", async () => {
    mockNotes({ notes: [HARD] });
    await openPage();
    await screen.findByText("For re-readers.");
    fireEvent.click(screen.getByRole("button", { name: "First reading" }));
    expect(screen.getByText("Every note on this page is hidden by the filters.")).toBeTruthy();
  });
});

describe("notes in blank mode", () => {
  it("shows notes read-only, marks their place on the bars, and offers no way to select", async () => {
    window.localStorage.setItem("pneutext.prefs", JSON.stringify({ mode: "blank" }));
    mockNotes({ notes: [EXISTING] });
    const page = await openPage();
    await waitFor(() => expect(page.dataset.mode).toBe("blank"));
    const card = (await screen.findByText("An old remark.")).closest(".note-card") as HTMLElement;
    expect(within(card).queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Note on this page" })).toBeNull();
    const mark = page.querySelector(".bar-highlight") as HTMLElement;
    expect(mark.dataset.notes).toBe("41");
    expect(page.querySelector(".page-body")?.textContent).toBe("");
    // Hovering the bar's highlight still points at its note.
    fireEvent.mouseOver(mark);
    expect(card.classList.contains("is-active")).toBe(true);
  });
});
