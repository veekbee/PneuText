import { describe, expect, it } from "vitest";

import { type LineMark, splitLine, stripes } from "../src/lib/highlights";
import { layoutLine } from "../src/lib/pageLayout";

function mark(id: number, start: number, end: number, typeId = 1): LineMark {
  return { annotation_id: id, type_id: typeId, start, end };
}

function summary(length: number, marks: LineMark[]): [number, number, number[]][] {
  return splitLine(length, marks).map((piece) => [
    piece.start,
    piece.end,
    piece.marks.map((item) => item.annotation_id),
  ]);
}

describe("splitLine", () => {
  it("returns the whole line as one plain piece when nothing is highlighted", () => {
    expect(summary(20, [])).toEqual([[0, 20, []]]);
  });

  it("cuts around a single highlight", () => {
    expect(summary(20, [mark(1, 5, 9)])).toEqual([
      [0, 5, []],
      [5, 9, [1]],
      [9, 20, []],
    ]);
  });

  it("gives a nested span's piece to both notes", () => {
    expect(summary(20, [mark(1, 2, 18), mark(2, 6, 10)])).toEqual([
      [0, 2, []],
      [2, 6, [1]],
      [6, 10, [1, 2]],
      [10, 18, [1]],
      [18, 20, []],
    ]);
  });

  it("gives the shared part of partly overlapping spans to both notes", () => {
    expect(summary(20, [mark(1, 0, 10), mark(2, 6, 20)])).toEqual([
      [0, 6, [1]],
      [6, 10, [1, 2]],
      [10, 20, [2]],
    ]);
  });

  it("handles three notes that start or end together", () => {
    expect(summary(12, [mark(1, 0, 12), mark(2, 0, 6), mark(3, 6, 12)])).toEqual([
      [0, 6, [1, 2]],
      [6, 12, [1, 3]],
    ]);
  });

  it("covers the line exactly once, with no empty pieces", () => {
    const pieces = splitLine(30, [mark(1, 3, 12), mark(2, 8, 25), mark(3, 8, 9), mark(4, 25, 30)]);
    expect(pieces[0]?.start).toBe(0);
    expect(pieces[pieces.length - 1]?.end).toBe(30);
    for (const [index, piece] of pieces.entries()) {
      expect(piece.end).toBeGreaterThan(piece.start);
      if (index > 0) expect(piece.start).toBe(pieces[index - 1]?.end);
    }
  });

  it("clamps marks to the line and ignores empty ones", () => {
    expect(summary(10, [mark(1, -4, 3), mark(2, 8, 99), mark(3, 5, 5)])).toEqual([
      [0, 3, [1]],
      [3, 8, []],
      [8, 10, [2]],
    ]);
  });
});

describe("stripes", () => {
  const colorOf = (typeId: number): string => ["", "red", "blue"][typeId] ?? "gray";

  it("is nothing for plain text", () => {
    expect(stripes([], [], 0, colorOf)).toBeUndefined();
  });

  it("paints each note in its own band, leaving other bands clear", () => {
    const marks = [mark(1, 0, 10, 1), mark(2, 6, 20, 2)];
    const drawn = layoutLine(
      {
        kind: "paragraph",
        line_no: 1,
        starts_paragraph: false,
        ends_paragraph: false,
        length: 20,
        highlights: marks,
      },
      20,
    );
    expect(drawn.bands).toBe(2);
    expect(stripes([marks[0] as LineMark], drawn.highlights, 2, colorOf)).toBe(
      "linear-gradient(to bottom, red 0% 50%, transparent 50% 100%)",
    );
    expect(stripes(marks, drawn.highlights, 2, colorOf)).toBe(
      "linear-gradient(to bottom, red 0% 50%, blue 50% 100%)",
    );
  });
});
