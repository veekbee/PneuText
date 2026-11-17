// The page's notes, in reading order of their spans. Each note expands in place to edit.
import { type CSSProperties, useEffect, useRef } from "react";

import type { Backlink, Figure, Note, NoteType, NoteUpdateInput, PassageLink } from "../api/client";
import { BacklinkList, PassageLinkList } from "../links/PageLinksList";
import { isEmptyBody, NoteBody, type NoteEnv } from "./NoteBody";
import { NoteEditor } from "./NoteEditor";

export interface NotesPanelProps {
  notes: Note[];
  /** How many notes the filters are hiding on this page. */
  hiddenCount: number;
  types: NoteType[];
  versionId: number;
  workCode: string;
  figures: Figure[];
  env: NoteEnv;
  page: number;
  /** Notes that refer to this page, and passages linked to it (already filtered). */
  backlinks: Backlink[];
  passageLinks: PassageLink[];
  /** Whether a backlink is one the reader's filters let through. */
  showBacklink: (backlink: Backlink) => boolean;
  onDeleteLink: (linkId: number) => void;
  /** In blank mode notes are read-only. */
  readOnly: boolean;
  activeNotes: number[];
  editingNote: number | null;
  /** The note to bring into view (after a click on its highlight). */
  scrollTo: { note: number; tick: number } | null;
  saving: boolean;
  error: string | null;
  statusFilter: "draft" | "ready" | null;
  onStatusFilter: (status: "draft" | "ready" | null) => void;
  onHover: (notes: number[]) => void;
  onEdit: (note: number | null) => void;
  onSave: (note: number, changes: NoteUpdateInput) => void;
  onDelete: (note: number) => void;
  onReselect: (note: number) => void;
  onNewPageNote: () => void;
  onNewChapterNote: (() => void) | null;
}

function placeOf(note: Note, page: number): string {
  if (note.scope === "page") return "Page";
  if (note.scope === "chapter") return "Chapter";
  if (note.start === null) return "";
  if (note.start.page !== page) return `from p. ${note.start.page}`;
  return note.start.line_no === null ? "" : `line ${note.start.line_no}`;
}

function NoteCard({
  note,
  type,
  props,
}: {
  note: Note;
  type: NoteType | undefined;
  props: NotesPanelProps;
}) {
  const ref = useRef<HTMLLIElement>(null);
  const editing = props.editingNote === note.id && !props.readOnly;
  const active = props.activeNotes.includes(note.id);
  const scrollTick = props.scrollTo?.note === note.id ? props.scrollTo.tick : null;

  useEffect(() => {
    if (scrollTick !== null) ref.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [scrollTick]);

  const pending = note.id < 0; // shown at once, before the server confirms
  return (
    <li
      ref={ref}
      className={["note-card", active ? "is-active" : "", pending ? "is-pending" : ""].join(" ")}
      style={{ "--type-color": type?.color ?? "var(--ink-quiet)" } as CSSProperties}
      data-note-id={note.id}
      onMouseEnter={() => props.onHover([note.id])}
      onMouseLeave={() => props.onHover([])}
    >
      <header className="note-head">
        <span className="note-type">{type?.name ?? "Note"}</span>
        <span className="note-place quiet">{placeOf(note, props.page)}</span>
        {note.level === 2 && (
          <span className="badge" title="Assumes you know the whole book">
            Have read
          </span>
        )}
        {note.status === "draft" && <span className="badge">Draft</span>}
        {!props.readOnly && !editing && !pending && (
          <button type="button" className="quiet-button" onClick={() => props.onEdit(note.id)}>
            Edit
          </button>
        )}
      </header>
      {editing ? (
        <NoteEditor
          note={note}
          types={props.types}
          env={props.env}
          workCode={props.workCode}
          otherNotes={props.notes.filter((other) => other.id !== note.id && other.id > 0)}
          figures={props.figures}
          saving={props.saving}
          error={props.error}
          onSave={(changes) => props.onSave(note.id, changes)}
          onCancel={() => props.onEdit(null)}
          onDelete={() => props.onDelete(note.id)}
          onReselect={note.scope === "span" ? () => props.onReselect(note.id) : undefined}
        />
      ) : isEmptyBody(note.body) ? (
        <p className="quiet note-empty">Highlight only.</p>
      ) : (
        <NoteBody body={note.body} env={props.env} />
      )}
      {!editing && note.tags.length > 0 && (
        <p className="note-tags quiet">{note.tags.map((tag) => `#${tag}`).join(" ")}</p>
      )}
      {!editing && note.backlinks.some(props.showBacklink) && (
        <section className="note-backlinks" aria-label="Referred to by">
          <h3>Referred to by</h3>
          <BacklinkList
            versionId={props.versionId}
            backlinks={note.backlinks.filter(props.showBacklink)}
            types={props.types}
          />
        </section>
      )}
    </li>
  );
}

export function NotesPanel(props: NotesPanelProps) {
  const typeById = new Map(props.types.map((type) => [type.id, type]));
  return (
    <aside className="notes-panel" aria-label="Notes">
      <header className="panel-head">
        <h2>Notes</h2>
        <label className="status-filter">
          Show
          <select
            value={props.statusFilter ?? ""}
            onChange={(event) =>
              props.onStatusFilter(
                event.target.value === "draft" || event.target.value === "ready"
                  ? event.target.value
                  : null,
              )
            }
          >
            <option value="">All</option>
            <option value="draft">Drafts</option>
            <option value="ready">Ready</option>
          </select>
        </label>
      </header>
      {props.notes.length === 0 ? (
        <p className="quiet">
          {props.hiddenCount > 0
            ? "Every note on this page is hidden by the filters."
            : props.readOnly
              ? "No notes on this page."
              : "No notes on this page yet. Select some text to add one."}
        </p>
      ) : (
        <ol className="note-list">
          {props.notes.map((note) => (
            <NoteCard key={note.id} note={note} type={typeById.get(note.type_id)} props={props} />
          ))}
        </ol>
      )}
      {props.notes.length > 0 && props.hiddenCount > 0 && (
        <p className="quiet">
          {props.hiddenCount} more {props.hiddenCount === 1 ? "note is" : "notes are"} hidden by
          the filters.
        </p>
      )}
      {props.backlinks.length > 0 && (
        <section className="panel-section" aria-label="Referred to from">
          <h2>Referred to from</h2>
          <BacklinkList versionId={props.versionId} backlinks={props.backlinks} types={props.types} />
        </section>
      )}
      {props.passageLinks.length > 0 && (
        <section className="panel-section" aria-label="Linked passages">
          <h2>Linked passages</h2>
          <PassageLinkList
            versionId={props.versionId}
            links={props.passageLinks}
            readOnly={props.readOnly}
            onDelete={props.onDeleteLink}
          />
        </section>
      )}
      {!props.readOnly && (
        <div className="panel-actions">
          <button type="button" className="quiet-button" onClick={props.onNewPageNote}>
            Note on this page
          </button>
          {props.onNewChapterNote && (
            <button type="button" className="quiet-button" onClick={props.onNewChapterNote}>
              Note on this chapter
            </button>
          )}
        </div>
      )}
    </aside>
  );
}
