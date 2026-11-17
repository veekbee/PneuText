// One print page, drawn to the print edition's shape.
// Takes the page as plain data and never calls the API, so a static edition can reuse it.
import { type CSSProperties, useLayoutEffect, useRef } from "react";

import type { TextLine } from "../api/client";

export interface PageViewProps {
  page: number;
  measure: number;
  lines: TextLine[];
  /** A line to mark as the target of a reference. */
  targetLine?: number | null;
}

const GUTTER_EVERY = 5;

function isText(line: TextLine): boolean {
  return line.kind === "paragraph" || line.kind === "synopsis";
}

function Line({ line, isTarget }: { line: TextLine; isTarget: boolean }) {
  switch (line.kind) {
    case "chapter_number":
      return <div className="furniture chapter-number">{line.text}</div>;
    case "ornament":
      return <div className="furniture ornament" role="presentation" />;
    case "rule":
      return <div className="furniture rule" role="presentation" />;
    default: {
      const classes = ["line", line.kind];
      if (line.starts_paragraph && line.kind === "paragraph") classes.push("indent");
      // Print is justified: every line but a paragraph's last runs the full measure.
      classes.push(line.ends_paragraph ? "last" : "full");
      if (isTarget) classes.push("is-target");
      const lineNo = line.line_no ?? undefined;
      return (
        <div
          className={classes.join(" ")}
          id={lineNo === undefined ? undefined : `l${lineNo}`}
          data-line-no={lineNo}
          data-gutter={
            lineNo !== undefined && lineNo % GUTTER_EVERY === 0 ? lineNo : undefined
          }
          data-segment-id={line.segment_id}
          data-start-offset={line.start_offset}
        >
          {line.text}
        </div>
      );
    }
  }
}

export function PageView({ page, measure, lines, targetLine = null }: PageViewProps) {
  const style = { "--measure": measure } as CSSProperties;
  const body = useRef<HTMLDivElement>(null);

  // Justifying can only stretch a line. One that is naturally wider than the measure is
  // tightened instead, in em so the fit holds as the page scales with the window.
  useLayoutEffect(() => {
    for (const row of body.current?.querySelectorAll<HTMLElement>(".line") ?? []) {
      row.style.letterSpacing = "";
      const over = row.scrollWidth - row.clientWidth;
      const characters = [...(row.textContent ?? "")].length;
      if (over <= 0 || characters === 0) continue;
      const fontSize = Number.parseFloat(getComputedStyle(row).fontSize);
      row.style.letterSpacing = `${-(over + 1) / characters / fontSize}em`;
    }
  }, [lines]);

  return (
    <article className="page" style={style} aria-label={`Page ${page}`}>
      <div className="page-body" ref={body}>
        {lines.map((line) => (
          <Line
            key={line.id}
            line={line}
            isTarget={targetLine !== null && isText(line) && line.line_no === targetLine}
          />
        ))}
      </div>
      <footer className="page-number">{page}</footer>
    </article>
  );
}
