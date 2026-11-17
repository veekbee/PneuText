// Review: work through notes filtered by chapter, type, level, status and tag, and mark
// them draft or ready in bulk.
import { useState } from "react";

import { api, type NoteSummary } from "../api/client";
import { useChange, useNoteList, useNoteTypes, useTags, useVersion } from "../api/queries";
import { pagePath } from "../lib/route";
import { Link } from "../router";
import { Loading, VersionShell } from "../shell/VersionShell";

interface Filters {
  division_id: string;
  type_id: string;
  level: string;
  status: string;
  tag: string;
}

const NO_FILTERS: Filters = { division_id: "", type_id: "", level: "", status: "", tag: "" };

export function placeOf(note: { page: number | null; line_no: number | null; scope?: string }): string {
  if (note.page === null) return "";
  if (note.scope === "chapter") return `p. ${note.page} (chapter)`;
  if (note.scope === "page" || note.line_no === null) return `p. ${note.page}`;
  return `p. ${note.page}.${note.line_no}`;
}

export function ReviewView({ versionId }: { versionId: number }) {
  const version = useVersion(versionId);
  const types = useNoteTypes();
  const tags = useTags();
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const notes = useNoteList(versionId, { ...filters });
  const setStatus = useChange(({ ids, status }: { ids: number[]; status: "draft" | "ready" }) =>
    api.setNotesStatus(versionId, ids, status),
  );
  const typeName = new Map((types.data ?? []).map((type) => [type.id, type.name]));
  const listed = notes.data ?? [];
  // Only notes still in the list can be acted on.
  const selected = listed.filter((note) => chosen.has(note.id)).map((note) => note.id);

  function set(key: keyof Filters, value: string): void {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function toggle(note: NoteSummary): void {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(note.id)) next.delete(note.id);
      else next.add(note.id);
      return next;
    });
  }

  function mark(status: "draft" | "ready"): void {
    setStatus.mutate({ ids: selected, status }, { onSuccess: () => setChosen(new Set()) });
  }

  return (
    <VersionShell versionId={versionId} view="review" title="Review">
      <div className="filters" role="group" aria-label="Filters">
        <label>
          Chapter
          <select value={filters.division_id} onChange={(event) => set("division_id", event.target.value)}>
            <option value="">All</option>
            {(version.data?.divisions ?? []).map((division) => (
              <option key={division.id} value={division.id}>
                {division.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Type
          <select value={filters.type_id} onChange={(event) => set("type_id", event.target.value)}>
            <option value="">All</option>
            {(types.data ?? []).map((type) => (
              <option key={type.id} value={type.id}>
                {type.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Level
          <select value={filters.level} onChange={(event) => set("level", event.target.value)}>
            <option value="">All</option>
            <option value="1">First reading</option>
            <option value="2">Have read</option>
          </select>
        </label>
        <label>
          Status
          <select value={filters.status} onChange={(event) => set("status", event.target.value)}>
            <option value="">All</option>
            <option value="draft">Draft</option>
            <option value="ready">Ready</option>
          </select>
        </label>
        <label>
          Tag
          <select value={filters.tag} onChange={(event) => set("tag", event.target.value)}>
            <option value="">All</option>
            {(tags.data ?? []).map((tag) => (
              <option key={tag} value={tag}>
                {tag}
              </option>
            ))}
          </select>
        </label>
      </div>
      {setStatus.error && (
        <div role="alert" className="notice">
          <p>{setStatus.error.message}</p>
        </div>
      )}
      {notes.data === undefined ? (
        <Loading error={notes.error} />
      ) : (
        <>
          <div className="bulk" role="group" aria-label="Selected notes">
            <span>
              {listed.length} {listed.length === 1 ? "note" : "notes"}
              {selected.length > 0 && `, ${selected.length} selected`}
            </span>
            <button
              type="button"
              className="quiet-button"
              onClick={() =>
                setChosen(selected.length === listed.length ? new Set() : new Set(listed.map((n) => n.id)))
              }
              disabled={listed.length === 0}
            >
              {selected.length === listed.length && listed.length > 0 ? "Select none" : "Select all"}
            </button>
            <button type="button" disabled={selected.length === 0} onClick={() => mark("ready")}>
              Mark ready
            </button>
            <button type="button" disabled={selected.length === 0} onClick={() => mark("draft")}>
              Mark draft
            </button>
          </div>
          {listed.length === 0 ? (
            <p className="quiet">No notes match these filters.</p>
          ) : (
            <table className="data-table review">
              <thead>
                <tr>
                  <th aria-label="Selected" />
                  <th>Place</th>
                  <th>Type</th>
                  <th>For</th>
                  <th>Status</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {listed.map((note) => (
                  <tr key={note.id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Select the note at ${placeOf(note)}`}
                        checked={chosen.has(note.id)}
                        onChange={() => toggle(note)}
                      />
                    </td>
                    <td>
                      {note.page === null ? (
                        ""
                      ) : (
                        <Link to={pagePath(versionId, note.page, note.line_no)}>{placeOf(note)}</Link>
                      )}
                    </td>
                    <td>{typeName.get(note.type_id) ?? ""}</td>
                    <td>{note.level === 2 ? "Have read" : "First reading"}</td>
                    <td>{note.status === "ready" ? "Ready" : "Draft"}</td>
                    <td>
                      {note.excerpt || <span className="quiet">Highlight only</span>}
                      {note.tags.length > 0 && (
                        <span className="quiet"> {note.tags.map((tag) => `#${tag}`).join(" ")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </VersionShell>
  );
}
