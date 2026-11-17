import { type FormEvent, useEffect, useRef, useState } from "react";

import type { Figure, Note, NoteNode, NoteType, NoteUpdateInput } from "../api/client";
import { useRenderedBody } from "../api/queries";
import { NoteBody, type NoteEnv } from "./NoteBody";
import { ReferencePicker } from "./ReferencePicker";

interface NoteEditorProps {
  note: Note;
  types: NoteType[];
  env: NoteEnv;
  /** For the reference picker: the work's short code, other notes here, and figures. */
  workCode: string;
  otherNotes: Note[];
  figures: Figure[];
  saving: boolean;
  error: string | null;
  onSave: (changes: NoteUpdateInput) => void;
  onCancel: () => void;
  onDelete: () => void;
  /** Offered for notes on a passage: choose the passage again, keeping the note. */
  onReselect?: () => void;
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return settled;
}

export function NoteEditor(props: NoteEditorProps) {
  const { note, types, saving, error } = props;
  const [typeId, setTypeId] = useState(note.type_id);
  const [level, setLevel] = useState(note.level);
  const [status, setStatus] = useState(note.status);
  const [tags, setTags] = useState(note.tags.join(", "));
  const [body, setBody] = useState(note.body_md);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // The preview is drawn from the server's parse of what is typed, the same tree the
  // saved note and the export use.
  const settledBody = useDebounced(body, 250);
  const rendered = useRenderedBody(
    settledBody,
    note.version_id,
    note.id,
    settledBody !== note.body_md,
  );
  const textarea = useRef<HTMLTextAreaElement>(null);

  /** Put a reference where the cursor is (or over what is selected) in the note. */
  function insert(text: string): void {
    const field = textarea.current;
    const start = field?.selectionStart ?? body.length;
    const end = field?.selectionEnd ?? body.length;
    setBody(body.slice(0, start) + text + body.slice(end));
    window.requestAnimationFrame(() => {
      field?.focus();
      field?.setSelectionRange(start + text.length, start + text.length);
    });
  }
  const preview: NoteNode = settledBody === note.body_md ? note.body : (rendered.data ?? note.body);

  function onSubmit(event: FormEvent): void {
    event.preventDefault();
    props.onSave({
      type_id: typeId,
      level,
      status,
      body_md: body,
      tags: tags.split(","),
    });
  }

  return (
    <form className="note-editor" onSubmit={onSubmit} aria-label="Edit note">
      <div className="editor-row">
        <label>
          Type
          <select value={typeId} onChange={(event) => setTypeId(Number(event.target.value))}>
            {types.map((type) => (
              <option key={type.id} value={type.id}>
                {type.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          For
          <select value={level} onChange={(event) => setLevel(Number(event.target.value))}>
            <option value={1}>First reading</option>
            <option value={2}>Have read</option>
          </select>
        </label>
        <label>
          Status
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value === "ready" ? "ready" : "draft")}
          >
            <option value="draft">Draft</option>
            <option value="ready">Ready</option>
          </select>
        </label>
      </div>
      <label>
        Note
        <textarea
          ref={textarea}
          value={body}
          rows={6}
          autoFocus
          placeholder="Markdown. Leave empty for a bare highlight."
          onChange={(event) => setBody(event.target.value)}
        />
      </label>
      <label>
        Tags
        <input
          value={tags}
          placeholder="separated by commas"
          onChange={(event) => setTags(event.target.value)}
        />
      </label>
      <ReferencePicker
        workCode={props.workCode}
        notes={props.otherNotes}
        types={types}
        figures={props.figures}
        onInsert={insert}
      />
      {body.trim() !== "" && (
        <section className="note-preview" aria-label="Preview">
          <NoteBody body={preview} env={props.env} />
        </section>
      )}
      {error !== null && (
        <p role="alert" className="editor-error">
          {error}
        </p>
      )}
      <div className="editor-actions">
        <button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button type="button" className="quiet-button" onClick={props.onCancel}>
          Cancel
        </button>
        {props.onReselect && (
          <button type="button" className="quiet-button" onClick={props.onReselect}>
            Re-select passage
          </button>
        )}
        {confirmingDelete ? (
          <button type="button" className="danger-button" onClick={props.onDelete}>
            Really delete
          </button>
        ) : (
          <button type="button" className="quiet-button" onClick={() => setConfirmingDelete(true)}>
            Delete
          </button>
        )}
      </div>
    </form>
  );
}
