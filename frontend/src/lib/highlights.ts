// Splitting a line at highlight boundaries, so each piece knows which notes cover it.
import type { DrawnHighlight } from "./pageLayout";

export interface LineMark {
  annotation_id: number;
  type_id: number;
  /** Offsets within the line, in code points. */
  start: number;
  end: number;
}

export interface Piece {
  start: number;
  end: number;
  /** The notes covering this piece, in the order given; empty for plain text. */
  marks: LineMark[];
}

/** Cut the range 0..length at every highlight boundary. Pieces cover it exactly once. */
export function splitLine(length: number, marks: LineMark[]): Piece[] {
  const clamp = (offset: number): number => Math.max(0, Math.min(offset, length));
  const usable = marks
    .map((mark) => ({ ...mark, start: clamp(mark.start), end: clamp(mark.end) }))
    .filter((mark) => mark.end > mark.start);
  const cuts = new Set<number>([0, length]);
  for (const mark of usable) {
    cuts.add(mark.start);
    cuts.add(mark.end);
  }
  const edges = [...cuts].sort((a, b) => a - b);
  const pieces: Piece[] = [];
  for (let index = 0; index + 1 < edges.length; index += 1) {
    const start = edges[index] as number;
    const end = edges[index + 1] as number;
    if (end === start) continue;
    pieces.push({
      start,
      end,
      marks: usable.filter((mark) => mark.start <= start && mark.end >= end),
    });
  }
  return pieces;
}

/**
 * The background for a piece covered by several notes: one horizontal stripe per band, so
 * overlapping highlights stay apart, as they do on the bars of blank mode.
 */
export function stripes(
  marks: LineMark[],
  drawn: DrawnHighlight[],
  bands: number,
  colorOf: (typeId: number) => string,
): string | undefined {
  if (marks.length === 0 || bands === 0) return undefined;
  const colors: (string | null)[] = Array.from({ length: bands }, () => null);
  for (const mark of marks) {
    const band = drawn.find((item) => item.annotation_id === mark.annotation_id)?.band;
    if (band !== undefined) colors[band] = colorOf(mark.type_id);
  }
  const stops = colors.map((color, band) => {
    const from = (band / bands) * 100;
    const to = ((band + 1) / bands) * 100;
    return `${color ?? "transparent"} ${from}% ${to}%`;
  });
  return `linear-gradient(to bottom, ${stops.join(", ")})`;
}
