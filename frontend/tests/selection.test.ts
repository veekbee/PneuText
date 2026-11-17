import { describe, expect, it } from "vitest";

import { readSelection, referenceFor, spanFromRows } from "../src/lib/selection";
import { line } from "./helpers";

const CLEF = "\u{1D11E}";

// Two paragraphs: segment 10 on three lines, segment 20 on one, with a rule between.
const LINES = [
  line("alpha beta", { id: 1, segment_id: 10, start_offset: 0, line_no: 1 }),
  line(`gamma ${CLEF} delta`, { id: 2, segment_id: 10, start_offset: 11, line_no: 2 }),
  line("epsilon", { id: 3, segment_id: 10, start_offset: 25, line_no: 3 }),
  line("", { id: 4, segment_id: 15, kind: "rule", line_no: null }),
  line("zeta eta", { id: 5, segment_id: 20, start_offset: 0, line_no: 4 }),
];

describe("spanFromRows", () => {
  it("makes a span within one line", () => {
    const found = spanFromRows(LINES, { row: 0, utf16: 6 }, { row: 0, utf16: 10 });
    expect(found?.span).toEqual({
      start_segment_id: 10,
      start_offset: 6,
      end_segment_id: 10,
      end_offset: 10,
      exact: "beta",
    });
    expect(found?.marks).toEqual([{ lineId: 1, start: 6, end: 10 }]);
  });

  it("joins print lines of one paragraph with a single space", () => {
    const found = spanFromRows(LINES, { row: 0, utf16: 6 }, { row: 1, utf16: 5 });
    expect(found?.span).toMatchObject({ start_offset: 6, end_offset: 16, exact: "beta gamma" });
    expect(found?.marks).toEqual([
      { lineId: 1, start: 6, end: 10 },
      { lineId: 2, start: 0, end: 5 },
    ]);
  });

  it("converts UTF-16 positions after an astral character into code points", () => {
    // "delta" starts at UTF-16 index 9 of its line, but at code point 8.
    const start = LINES[1]?.text.indexOf("delta") ?? -1;
    expect(start).toBe(9);
    const found = spanFromRows(LINES, { row: 1, utf16: start }, { row: 1, utf16: start + 5 });
    expect(found?.span).toMatchObject({ start_offset: 11 + 8, end_offset: 11 + 13, exact: "delta" });
    expect(found?.marks).toEqual([{ lineId: 2, start: 8, end: 13 }]);
  });

  it("joins paragraphs with a newline and passes over furniture", () => {
    const found = spanFromRows(LINES, { row: 2, utf16: 0 }, { row: 4, utf16: 4 });
    expect(found?.span).toEqual({
      start_segment_id: 10,
      start_offset: 25,
      end_segment_id: 20,
      end_offset: 4,
      exact: "epsilon\n\nzeta",
    });
    expect(found?.marks.map((item) => item.lineId)).toEqual([3, 5]);
  });

  it("accepts the two points in either order", () => {
    const forwards = spanFromRows(LINES, { row: 0, utf16: 6 }, { row: 1, utf16: 5 });
    const backwards = spanFromRows(LINES, { row: 1, utf16: 5 }, { row: 0, utf16: 6 });
    expect(backwards?.span).toEqual(forwards?.span);
  });

  it("starts with the next line when the selection begins at a line's end", () => {
    const found = spanFromRows(LINES, { row: 0, utf16: 10 }, { row: 1, utf16: 5 });
    expect(found?.span).toMatchObject({ start_offset: 11, exact: "gamma" });
  });

  it("ends with the previous line when the selection stops at a line's start", () => {
    const found = spanFromRows(LINES, { row: 0, utf16: 6 }, { row: 1, utf16: 0 });
    expect(found?.span).toMatchObject({ end_offset: 10, exact: "beta" });
  });

  it("moves off furniture at either end", () => {
    const found = spanFromRows(LINES, { row: 3, utf16: 0 }, { row: 4, utf16: 4 });
    expect(found?.span).toMatchObject({ start_segment_id: 20, start_offset: 0, exact: "zeta" });
    const before = spanFromRows(LINES, { row: 2, utf16: 3 }, { row: 3, utf16: 0 });
    expect(before?.span).toMatchObject({ end_segment_id: 10, end_offset: 32, exact: "ilon" });
  });

  it("reports which print lines the passage starts and ends on", () => {
    const found = spanFromRows(LINES, { row: 0, utf16: 6 }, { row: 2, utf16: 3 });
    expect([found?.first.line_no, found?.last.line_no]).toEqual([1, 3]);
  });

  it("is nothing when the selection is empty or only furniture", () => {
    expect(spanFromRows(LINES, { row: 1, utf16: 4 }, { row: 1, utf16: 4 })).toBeNull();
    expect(spanFromRows(LINES, { row: 3, utf16: 0 }, { row: 3, utf16: 0 })).toBeNull();
    expect(spanFromRows(LINES, { row: 0, utf16: 10 }, { row: 1, utf16: 0 })).toBeNull();
  });
});

describe("referenceFor", () => {
  it("names a single line", () => {
    expect(referenceFor("fx", { page: 45, line_no: 12 }, { page: 45, line_no: 12 })).toBe(
      "{{fx:45.12}}",
    );
  });

  it("names a range of lines, also across pages", () => {
    expect(referenceFor("fx", { page: 45, line_no: 12 }, { page: 45, line_no: 14 })).toBe(
      "{{fx:45.12-45.14}}",
    );
    expect(referenceFor("fx", { page: 45, line_no: 30 }, { page: 46, line_no: 3 })).toBe(
      "{{fx:45.30-46.3}}",
    );
  });
});

describe("readSelection", () => {
  function page(): HTMLElement {
    const body = document.createElement("div");
    const rows = ["alpha beta", "gamma delta", "epsilon"].map((text, index) => {
      const row = document.createElement("div");
      row.dataset.row = String(index);
      return { row, text };
    });
    // The second row is cut into pieces, as a highlighted line is.
    rows[0]?.row.append(document.createTextNode("alpha beta"));
    const piece = document.createElement("span");
    piece.textContent = "delta";
    rows[1]?.row.append(document.createTextNode("gamma "), piece);
    rows[2]?.row.append(document.createTextNode("epsilon"));
    body.append(...rows.map((item) => item.row));
    document.body.replaceChildren(body);
    return body;
  }

  function select(startNode: Node, startOffset: number, endNode: Node, endOffset: number): void {
    const range = document.createRange();
    range.setStart(startNode, startOffset);
    range.setEnd(endNode, endOffset);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
  }

  it("finds the rows and positions of a selection within one row", () => {
    const body = page();
    const text = body.children[0]?.firstChild as Text;
    select(text, 6, text, 10);
    const read = readSelection(body);
    expect([read?.from, read?.to]).toEqual([
      { row: 0, utf16: 6 },
      { row: 0, utf16: 10 },
    ]);
  });

  it("counts from the start of the row even inside a highlighted piece", () => {
    const body = page();
    const start = body.children[0]?.firstChild as Text;
    const piece = body.children[1]?.querySelector("span")?.firstChild as Text;
    select(start, 6, piece, 3);
    const read = readSelection(body);
    expect([read?.from, read?.to]).toEqual([
      { row: 0, utf16: 6 },
      { row: 1, utf16: 9 },
    ]);
  });

  it("is nothing for a collapsed selection or one outside the page", () => {
    const body = page();
    const text = body.children[0]?.firstChild as Text;
    select(text, 3, text, 3);
    expect(readSelection(body)).toBeNull();
    const elsewhere = document.createElement("p");
    elsewhere.textContent = "not the page";
    document.body.append(elsewhere);
    select(elsewhere.firstChild as Text, 0, elsewhere.firstChild as Text, 3);
    expect(readSelection(body)).toBeNull();
  });
});
