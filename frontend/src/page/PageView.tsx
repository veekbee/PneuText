// One print page, drawn to the print edition's shape, in text mode or blank mode.
// Takes the page as plain data and never calls the API, so a static edition can reuse it.
//
// Both modes draw the same rows at the same pitch from the same measure, so switching
// modes moves nothing. Blank mode is given the shape projection, which has no text.
import { type CSSProperties, useLayoutEffect, useRef } from "react";

import type { ShapeLine, TextLine } from "../api/client";
import { type DrawnLine, INDENT, isTextKind, layoutLine } from "../lib/pageLayout";

interface CommonProps {
  page: number;
  measure: number;
  /** A line to mark as the target of a reference. */
  targetLine?: number | null;
}

export type PageViewProps = CommonProps &
  ({ mode: "text"; lines: TextLine[] } | { mode: "blank"; lines: ShapeLine[] });

const GUTTER_EVERY = 5;

function percent(fraction: number): string {
  return `${Math.round(fraction * 1e6) / 1e4}%`;
}

function rowAttributes(line: ShapeLine | TextLine, isTarget: boolean, extra: string[]) {
  const classes = ["line", line.kind, ...extra];
  if (line.starts_paragraph && line.kind === "paragraph") classes.push("indent");
  // Print is justified: every line but a paragraph's last runs the full measure.
  classes.push(line.ends_paragraph ? "last" : "full");
  if (isTarget) classes.push("is-target");
  const lineNo = line.line_no ?? undefined;
  return {
    className: classes.join(" "),
    id: lineNo === undefined ? undefined : `l${lineNo}`,
    "data-line-no": lineNo,
    "data-gutter": lineNo !== undefined && lineNo % GUTTER_EVERY === 0 ? lineNo : undefined,
  };
}

function Furniture({ kind, label }: { kind: string; label?: string }) {
  switch (kind) {
    case "chapter_number":
      // In blank mode there is no label: the number is drawn as a fixed placeholder.
      return (
        <div className="furniture chapter-number">
          {label ?? <span className="placeholder" role="presentation" />}
        </div>
      );
    case "ornament":
      return <div className="furniture ornament" role="presentation" />;
    default:
      return <div className="furniture rule" role="presentation" />;
  }
}

function TextRow({ line, isTarget }: { line: TextLine; isTarget: boolean }) {
  if (!isTextKind(line.kind)) return <Furniture kind={line.kind} label={line.text} />;
  return (
    <div
      {...rowAttributes(line, isTarget, [])}
      style={{ "--length": line.length } as CSSProperties}
      data-segment-id={line.segment_id}
      data-start-offset={line.start_offset}
    >
      {line.text}
    </div>
  );
}

function Bar({ drawn }: { drawn: DrawnLine }) {
  const bar = { left: percent(drawn.x0), width: percent(drawn.x1 - drawn.x0) };
  return (
    <>
      <span className="bar" style={bar} />
      {drawn.highlights.map((highlight) => (
        <span
          key={highlight.annotation_id}
          className="bar-highlight"
          data-annotation-id={highlight.annotation_id}
          data-type-id={highlight.type_id}
          style={
            {
              left: percent(highlight.x0),
              width: percent(highlight.x1 - highlight.x0),
              "--band": highlight.band,
              "--bands": drawn.bands,
            } as CSSProperties
          }
        />
      ))}
    </>
  );
}

function BlankRow({
  line,
  measure,
  isTarget,
}: {
  line: ShapeLine;
  measure: number;
  isTarget: boolean;
}) {
  if (!isTextKind(line.kind)) return <Furniture kind={line.kind} />;
  return (
    <div {...rowAttributes(line, isTarget, ["blank"])}>
      <Bar drawn={layoutLine(line, measure)} />
    </div>
  );
}

export function PageView(props: PageViewProps) {
  const { page, measure, targetLine = null } = props;
  const style = { "--measure": Math.max(measure, 1), "--indent": INDENT } as CSSProperties;
  const body = useRef<HTMLDivElement>(null);
  const isTarget = (line: ShapeLine | TextLine): boolean =>
    targetLine !== null && isTextKind(line.kind) && line.line_no === targetLine;

  // Justifying can only stretch a line. One that is naturally wider than the measure is
  // tightened instead, in em so the fit holds as the page scales with the window.
  useLayoutEffect(() => {
    for (const row of body.current?.querySelectorAll<HTMLElement>(".line:not(.blank)") ?? []) {
      row.style.letterSpacing = "";
      const over = row.scrollWidth - row.clientWidth;
      const characters = [...(row.textContent ?? "")].length;
      if (over <= 0 || characters === 0) continue;
      const fontSize = Number.parseFloat(getComputedStyle(row).fontSize);
      row.style.letterSpacing = `${-(over + 1) / characters / fontSize}em`;
    }
  }, [props.lines, props.mode]);

  return (
    <article
      className="page"
      style={style}
      aria-label={`Page ${page}`}
      data-mode={props.mode}
    >
      <div className="page-body" ref={body}>
        {props.mode === "text"
          ? props.lines.map((line) => (
              <TextRow key={line.id} line={line} isTarget={isTarget(line)} />
            ))
          : props.lines.map((line) => (
              <BlankRow key={line.id} line={line} measure={measure} isTarget={isTarget(line)} />
            ))}
      </div>
      <footer className="page-number">{page}</footer>
    </article>
  );
}
