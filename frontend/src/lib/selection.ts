// Turning a selection on the page into a span the server can check.
//
// The quoted text is cut from what the reader actually selected, using the browser's own
// UTF-16 positions, while the offsets are converted to code points. The server compares
// the two, so a conversion mistake is caught there instead of misplacing a note.
import type { SpanInput, TextLine } from "../api/client";
import { isTextKind } from "./pageLayout";
import { utf16ToCodePoints } from "./offsets";

/** A position in a list of print lines: which line, and how far along in UTF-16 units. */
export interface RowPoint {
  row: number;
  utf16: number;
}

/** Where a new highlight falls on one line, in code points within the line. */
export interface RowMark {
  lineId: number;
  start: number;
  end: number;
}

export interface SpanSelection {
  span: SpanInput;
  marks: RowMark[];
  /** The print line the passage starts on and the one it ends on. */
  first: TextLine;
  last: TextLine;
}

function compare(a: RowPoint, b: RowPoint): number {
  return a.row - b.row || a.utf16 - b.utf16;
}

/**
 * The span between two points in a run of print lines (the lines of one page, or of
 * several consecutive pages). Returns null when nothing is selected.
 */
export function spanFromRows(lines: TextLine[], a: RowPoint, b: RowPoint): SpanSelection | null {
  let [from, to] = compare(a, b) <= 0 ? [a, b] : [b, a];
  const textOf = (row: number): string => lines[row]?.text ?? "";
  const isText = (row: number): boolean => {
    const line = lines[row];
    return line !== undefined && isTextKind(line.kind);
  };

  // A selection that starts at the very end of a line, or on furniture, starts with the
  // next line of text; one that ends at the very start of a line ends with the previous.
  while (from.row < to.row && (!isText(from.row) || from.utf16 >= textOf(from.row).length)) {
    from = { row: from.row + 1, utf16: 0 };
  }
  while (to.row > from.row && (!isText(to.row) || to.utf16 <= 0)) {
    to = { row: to.row - 1, utf16: textOf(to.row - 1).length };
  }
  const first = lines[from.row];
  const last = lines[to.row];
  if (first === undefined || last === undefined || !isText(from.row) || !isText(to.row)) {
    return null;
  }
  if (compare(from, to) >= 0) return null;

  let exact = "";
  const marks: RowMark[] = [];
  for (let row = from.row; row <= to.row; row += 1) {
    const line = lines[row] as TextLine;
    const startUnit = row === from.row ? from.utf16 : 0;
    const endUnit = row === to.row ? to.utf16 : line.text.length;
    if (row > from.row) {
      // One space stands between print lines of a paragraph; a newline between segments.
      exact += line.segment_id === (lines[row - 1] as TextLine).segment_id ? " " : "\n";
    }
    exact += line.text.slice(startUnit, endUnit);
    if (isTextKind(line.kind) && endUnit > startUnit) {
      marks.push({
        lineId: line.id,
        start: utf16ToCodePoints(line.text, startUnit),
        end: utf16ToCodePoints(line.text, endUnit),
      });
    }
  }

  return {
    span: {
      start_segment_id: first.segment_id,
      start_offset: first.start_offset + utf16ToCodePoints(first.text, from.utf16),
      end_segment_id: last.segment_id,
      end_offset: last.start_offset + utf16ToCodePoints(last.text, to.utf16),
      exact,
    },
    marks,
    first,
    last,
  };
}

/** How a note refers to a passage: `{{code:page.line}}` or `{{code:page.line-page.line}}`. */
export function referenceFor(
  workCode: string,
  from: { page: number; line_no: number | null },
  to: { page: number; line_no: number | null },
): string {
  const place = (at: { page: number; line_no: number | null }): string =>
    at.line_no === null ? String(at.page) : `${at.page}.${at.line_no}`;
  const start = place(from);
  const end = place(to);
  return start === end ? `{{${workCode}:${start}}}` : `{{${workCode}:${start}-${end}}}`;
}

/**
 * Read the browser's selection as two points among the page's rows. Rows are the
 * elements carrying `data-row`, the index of their line. Returns null when the selection
 * is empty or lies outside the page.
 */
export function readSelection(body: HTMLElement): { from: RowPoint; to: RowPoint; rect: DOMRect } | null {
  const selection = window.getSelection();
  if (selection === null || selection.rangeCount === 0 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  const rows = [...body.querySelectorAll<HTMLElement>("[data-row]")].filter((row) =>
    range.intersectsNode(row),
  );
  const firstRow = rows[0];
  const lastRow = rows[rows.length - 1];
  if (firstRow === undefined || lastRow === undefined) return null;

  const unitsBefore = (row: HTMLElement, node: Node, offset: number): number => {
    const before = document.createRange();
    before.selectNodeContents(row);
    before.setEnd(node, offset);
    return before.toString().length;
  };
  const from: RowPoint = {
    row: Number(firstRow.dataset.row),
    utf16: firstRow.contains(range.startContainer)
      ? unitsBefore(firstRow, range.startContainer, range.startOffset)
      : 0,
  };
  const to: RowPoint = {
    row: Number(lastRow.dataset.row),
    utf16: lastRow.contains(range.endContainer)
      ? unitsBefore(lastRow, range.endContainer, range.endOffset)
      : (lastRow.textContent ?? "").length,
  };
  // Some environments cannot measure a range; the popover then sits at the corner.
  const rect = range.getBoundingClientRect?.() ?? new DOMRect();
  return { from, to, rect };
}
