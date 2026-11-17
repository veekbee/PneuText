// Page shape: where each print line's bar and highlights fall, from line lengths alone.
//
// These rules are implemented a second time in Python (pneutext/core/shape.py) for the
// export. Both are held to tests/fixtures/shape_cases.json, so app and export draw the
// same page. Nothing here sees corpus text.

/** How far a paragraph's first line is indented, in characters of the measure. */
export const INDENT = 3;

export interface ShapeHighlightInput {
  annotation_id: number;
  type_id: number;
  start: number;
  end: number;
}

export interface ShapeLineInput {
  kind: string;
  line_no: number | null;
  starts_paragraph: boolean;
  ends_paragraph: boolean;
  length: number;
  highlights: ShapeHighlightInput[];
}

export interface DrawnHighlight {
  annotation_id: number;
  type_id: number;
  /** As fractions of the measure, like the bar they lie on. */
  x0: number;
  x1: number;
  /** Overlapping highlights stack as offset bands; this is the band's index. */
  band: number;
}

export interface DrawnLine {
  kind: string;
  line_no: number | null;
  /** The bar runs from x0 to x1, as fractions of the measure. */
  x0: number;
  x1: number;
  bands: number;
  highlights: DrawnHighlight[];
}

// Round half up, spelled out so Python and TypeScript agree to the last digit.
function round4(value: number): number {
  return Math.floor(value * 10000 + 0.5) / 10000;
}

export function isTextKind(kind: string): boolean {
  return kind === "paragraph" || kind === "synopsis";
}

export function layoutLine(line: ShapeLineInput, measure: number): DrawnLine {
  const width = Math.max(measure, 1);
  if (!isTextKind(line.kind)) {
    // Furniture is drawn as a fixed placeholder for its kind, across the measure.
    return { kind: line.kind, line_no: line.line_no, x0: 0, x1: 1, bands: 0, highlights: [] };
  }

  const indented = line.starts_paragraph && line.kind === "paragraph";
  const x0 = indented ? Math.min(INDENT / width, 1) : 0;
  // Print is justified: every line runs the full measure except a paragraph's last.
  const x1 = line.ends_paragraph ? Math.min(x0 + line.length / width, 1) : 1;

  const clamp = (offset: number): number => Math.max(0, Math.min(offset, line.length));
  const ordered = line.highlights
    .map((highlight) => {
      const start = clamp(highlight.start);
      return { highlight, start, end: Math.max(start, clamp(highlight.end)), key: clamp(highlight.end) };
    })
    .sort(
      (a, b) =>
        a.start - b.start || b.key - a.key || a.highlight.annotation_id - b.highlight.annotation_id,
    );

  const bandEnds: number[] = []; // for each band, where its last highlight ends
  const scale = line.length > 0 ? (x1 - x0) / line.length : 0;
  const highlights = ordered.map(({ highlight, start, end }) => {
    let band = bandEnds.findIndex((taken) => taken <= start);
    if (band === -1) band = bandEnds.length;
    bandEnds[band] = end;
    return {
      annotation_id: highlight.annotation_id,
      type_id: highlight.type_id,
      x0: round4(x0 + start * scale),
      x1: round4(x0 + end * scale),
      band,
    };
  });

  return {
    kind: line.kind,
    line_no: line.line_no,
    x0: round4(x0),
    x1: round4(x1),
    bands: bandEnds.length,
    highlights,
  };
}

export function layoutPage(lines: ShapeLineInput[], measure: number): DrawnLine[] {
  return lines.map((line) => layoutLine(line, measure));
}
