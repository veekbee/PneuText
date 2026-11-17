// Inserts a reference into a note: to a page or lines, to another note, or to a figure.
// The text form is what gets stored; the picker only writes it for the author.
import { useState } from "react";

import type { Figure, Note, NoteType } from "../api/client";

interface ReferencePickerProps {
  workCode: string;
  /** The notes beside the current page, to refer to. */
  notes: Note[];
  types: NoteType[];
  figures: Figure[];
  onInsert: (text: string) => void;
}

// 45, 45.12, 292-293, 45.12-46.3
const PLACE = /^\d+(\.\d+)?(\s*-\s*\d+(\.\d+)?)?$/;

export function ReferencePicker({ workCode, notes, types, figures, onInsert }: ReferencePickerProps) {
  const [place, setPlace] = useState("");
  const typeName = new Map(types.map((type) => [type.id, type.name]));
  const valid = PLACE.test(place.trim());

  // The picker sits inside the note's form, so it must not be a form itself: a form
  // within a form would save the note instead of inserting the reference.
  function insertPlace(): void {
    if (!valid) return;
    onInsert(`{{${workCode}:${place.trim().replace(/\s+/g, "")}}}`);
    setPlace("");
  }

  return (
    <fieldset className="reference-picker">
      <legend>Insert a reference</legend>
      <div className="picker-row">
        <label>
          Page or lines
          <input
            value={place}
            placeholder="45, 45.12, 292-293"
            aria-invalid={place !== "" && !valid}
            onChange={(event) => setPlace(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              event.preventDefault(); // Enter inserts; it does not save the note
              insertPlace();
            }}
          />
        </label>
        <button type="button" className="quiet-button" disabled={!valid} onClick={insertPlace}>
          Insert
        </button>
      </div>
      <label>
        Another note
        <select
          value=""
          disabled={notes.length === 0}
          onChange={(event) => event.target.value && onInsert(`{{note:${event.target.value}}}`)}
        >
          <option value="">{notes.length === 0 ? "No other notes on this page" : "Choose…"}</option>
          {notes.map((note) => (
            <option key={note.id} value={note.id}>
              {typeName.get(note.type_id) ?? "Note"}
              {note.start?.line_no != null && `, line ${note.start.line_no}`}
              {note.body_md && `: ${note.body_md.replace(/\s+/g, " ").slice(0, 40)}`}
            </option>
          ))}
        </select>
      </label>
      <label>
        A figure
        <select
          value=""
          disabled={figures.length === 0}
          onChange={(event) => {
            const [how, label] = event.target.value.split(":", 2);
            const figure = figures.find((item) => item.label === label);
            if (!figure) return;
            onInsert(how === "place" ? `![${figure.caption}](fig:${figure.label})` : `{{fig:${figure.label}}}`);
          }}
        >
          <option value="">{figures.length === 0 ? "No figures in the library" : "Choose…"}</option>
          {figures.map((figure) => (
            <optgroup key={figure.label} label={figure.caption || figure.label}>
              <option value={`place:${figure.label}`}>Place {figure.label} here</option>
              <option value={`cite:${figure.label}`}>Refer to {figure.label}</option>
            </optgroup>
          ))}
        </select>
      </label>
    </fieldset>
  );
}
