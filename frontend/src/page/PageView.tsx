// One print page, drawn to the print edition's shape, in text mode or blank mode.
// Takes the page as plain data and never calls the API, so a static edition can reuse it.
//
// Both modes draw the same rows at the same pitch from the same measure, so switching
// modes moves nothing. Blank mode is given the shape projection, which has no text.
import { type CSSProperties, type MouseEvent, useLayoutEffect, useRef } from "react";

import type { Highlight, MentionMark, ShapeLine, TextLine } from "../api/client";
import { splitLine, stripes } from "../lib/highlights";
import { sliceCodePoints } from "../lib/offsets";
import { type DrawnLine, INDENT, isTextKind, layoutLine } from "../lib/pageLayout";

interface CommonProps {
  page: number;
  measure: number;
  /** A line to mark as the target of a reference. */
  targetLine?: number | null;
  /** Each note type's color, by type id. */
  typeColors?: Record<number, string>;
  /** Each entity category's color, by category id, for the underline on mentions. */
  categoryColors?: Record<number, string>;
  /** Notes to emphasize (the ones hovered in the side panel). */
  activeNotes?: number[];
  onHoverNotes?: (notes: number[]) => void;
  onClickNotes?: (notes: number[]) => void;
}

export type PageViewProps = CommonProps &
  ({ mode: "text"; lines: TextLine[] } | { mode: "blank"; lines: ShapeLine[] });

const GUTTER_EVERY = 5;
const FALLBACK_COLOR = "#8a8a8a";

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

interface RowContext {
  measure: number;
  colorOf: (typeId: number) => string;
  categoryColorOf: (categoryId: number) => string;
  activeNotes: number[];
}

type NoteMark = Highlight & { kind: "note" };
type TagMark = MentionMark & { kind: "mention" };

function TextRow({
  line,
  row,
  isTarget,
  context,
}: {
  line: TextLine;
  row: number;
  isTarget: boolean;
  context: RowContext;
}) {
  if (!isTextKind(line.kind)) return <Furniture kind={line.kind} label={line.text} />;
  // The line is cut at highlight boundaries; a piece can belong to several notes, which
  // show as stacked stripes in the same bands blank mode uses.
  const drawn = layoutLine(line, context.measure);
  const marks: (NoteMark | TagMark)[] = [
    ...line.highlights.map((mark) => ({ ...mark, kind: "note" as const })),
    ...line.mentions.map((mark) => ({ ...mark, kind: "mention" as const })),
  ];
  const pieces = splitLine(line.length, marks);
  return (
    <div
      {...rowAttributes(line, isTarget, [])}
      style={{ "--length": line.length } as CSSProperties}
      data-row={row}
      data-segment-id={line.segment_id}
      data-start-offset={line.start_offset}
    >
      {pieces.map((piece) => {
        const text = sliceCodePoints(line.text, piece.start, piece.end);
        if (piece.marks.length === 0) return text;
        const noteMarks = piece.marks.filter((mark) => mark.kind === "note");
        const tags = piece.marks.filter((mark) => mark.kind === "mention");
        const notes = noteMarks.map((mark) => mark.annotation_id);
        const isActive = notes.some((note) => context.activeNotes.includes(note));
        const classes = [
          noteMarks.length > 0 ? "hl" : "",
          tags.length > 0 ? "mention" : "",
          isActive ? "is-active" : "",
        ];
        const tag = tags[0];
        return (
          <span
            key={piece.start}
            className={classes.filter(Boolean).join(" ")}
            data-notes={notes.length > 0 ? notes.join(" ") : undefined}
            data-mentions={
              tags.length > 0 ? tags.map((mark) => mark.mention_id).join(" ") : undefined
            }
            style={
              {
                backgroundImage: stripes(noteMarks, drawn.highlights, drawn.bands, (typeId) =>
                  `color-mix(in srgb, ${context.colorOf(typeId)} 55%, transparent)`,
                ),
                // Entity mentions show as a thin underline in their category's color.
                "--mention-color": tag ? context.categoryColorOf(tag.category_id) : undefined,
              } as CSSProperties
            }
          >
            {text}
          </span>
        );
      })}
    </div>
  );
}

function Bar({
  drawn,
  line,
  context,
}: {
  drawn: DrawnLine;
  line: ShapeLine;
  context: RowContext;
}) {
  const bar = { left: percent(drawn.x0), width: percent(drawn.x1 - drawn.x0) };
  // A mention is placed along the bar as a highlight is: by its share of the line.
  const along = (offset: number): number =>
    drawn.x0 + (line.length > 0 ? ((drawn.x1 - drawn.x0) * offset) / line.length : 0);
  return (
    <>
      <span className="bar" style={bar} />
      {line.mentions.map((mention) => (
        <span
          key={`m${mention.mention_id}`}
          className="bar-mention"
          data-mentions={mention.mention_id}
          style={{
            left: percent(along(mention.start)),
            width: percent(along(mention.end) - along(mention.start)),
            background: context.categoryColorOf(mention.category_id),
          }}
        />
      ))}
      {drawn.highlights.map((highlight) => (
        <span
          key={highlight.annotation_id}
          className={
            context.activeNotes.includes(highlight.annotation_id)
              ? "bar-highlight is-active"
              : "bar-highlight"
          }
          data-notes={highlight.annotation_id}
          data-annotation-id={highlight.annotation_id}
          data-type-id={highlight.type_id}
          style={
            {
              left: percent(highlight.x0),
              width: percent(highlight.x1 - highlight.x0),
              background: context.colorOf(highlight.type_id),
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
  isTarget,
  context,
}: {
  line: ShapeLine;
  isTarget: boolean;
  context: RowContext;
}) {
  if (!isTextKind(line.kind)) return <Furniture kind={line.kind} />;
  return (
    <div {...rowAttributes(line, isTarget, ["blank"])}>
      <Bar drawn={layoutLine(line, context.measure)} line={line} context={context} />
    </div>
  );
}

function notesAt(target: EventTarget | null): number[] {
  if (!(target instanceof Element)) return [];
  const marked = target.closest<HTMLElement>("[data-notes]");
  return (marked?.dataset.notes ?? "").split(" ").filter(Boolean).map(Number);
}

export function PageView(props: PageViewProps) {
  const { page, measure, targetLine = null, typeColors = {}, activeNotes = [] } = props;
  const categoryColors = props.categoryColors ?? {};
  const style = { "--measure": Math.max(measure, 1), "--indent": INDENT } as CSSProperties;
  const body = useRef<HTMLDivElement>(null);
  const isTarget = (line: ShapeLine | TextLine): boolean =>
    targetLine !== null && isTextKind(line.kind) && line.line_no === targetLine;
  const context: RowContext = {
    measure,
    colorOf: (typeId) => typeColors[typeId] ?? FALLBACK_COLOR,
    categoryColorOf: (categoryId) => categoryColors[categoryId] ?? FALLBACK_COLOR,
    activeNotes,
  };

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

  const { onHoverNotes, onClickNotes } = props;
  return (
    <article className="page" style={style} aria-label={`Page ${page}`} data-mode={props.mode}>
      <div
        className="page-body"
        ref={body}
        onMouseOver={onHoverNotes && ((event: MouseEvent) => onHoverNotes(notesAt(event.target)))}
        onMouseLeave={onHoverNotes && (() => onHoverNotes([]))}
        onClick={
          onClickNotes &&
          ((event: MouseEvent) => {
            const notes = notesAt(event.target);
            if (notes.length > 0) onClickNotes(notes);
          })
        }
      >
        {props.mode === "text"
          ? props.lines.map((line, row) => (
              <TextRow key={line.id} line={line} row={row} isTarget={isTarget(line)} context={context} />
            ))
          : props.lines.map((line) => (
              <BlankRow key={line.id} line={line} isTarget={isTarget(line)} context={context} />
            ))}
      </div>
      <footer className="page-number">{page}</footer>
    </article>
  );
}
