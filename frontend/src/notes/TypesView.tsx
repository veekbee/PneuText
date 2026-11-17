// Note types are data: the author can add, rename, recolor and merge them at any time.
import { type FormEvent, useState } from "react";

import { api, type NoteType, type NoteTypeInput, type NoteTypeUpdate } from "../api/client";
import { useChange, useNoteTypes } from "../api/queries";
import { InlineEdit } from "../shell/InlineEdit";
import { Loading, VersionShell } from "../shell/VersionShell";

const ROLES: [NoteType["role"], string][] = [
  ["note", "Note"],
  ["definition", "Definition (also in the glossary)"],
  ["chapter_title", "Chapter title"],
  ["chapter_summary", "Chapter summary"],
];

const NEW_TYPE: NoteTypeInput = { name: "", code: "", color: "#7a8a9a", role: "note" };

export function TypesView({ versionId }: { versionId: number }) {
  const types = useNoteTypes();
  const [draft, setDraft] = useState<NoteTypeInput>(NEW_TYPE);
  const create = useChange((input: NoteTypeInput) => api.createNoteType(input));
  const update = useChange(({ id, changes }: { id: number; changes: NoteTypeUpdate }) =>
    api.updateNoteType(id, changes),
  );
  const merge = useChange(({ id, into }: { id: number; into: number }) => api.mergeNoteType(id, into));
  const error = create.error ?? update.error ?? merge.error;
  const edit = (id: number, changes: NoteTypeUpdate): void => update.mutate({ id, changes });

  function onAdd(event: FormEvent): void {
    event.preventDefault();
    create.mutate(draft, { onSuccess: () => setDraft(NEW_TYPE) });
  }

  return (
    <VersionShell versionId={versionId} view="types" title="Note types">
      {error && (
        <div role="alert" className="notice">
          <p>{error.message}</p>
        </div>
      )}
      {types.data === undefined ? (
        <Loading error={types.error} />
      ) : (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>Color</th>
                <th>Name</th>
                <th>Code</th>
                <th>Kind</th>
                <th>Merge</th>
              </tr>
            </thead>
            <tbody>
              {types.data.map((type) => (
                <tr key={type.id}>
                  <td>
                    <input
                      type="color"
                      aria-label={`Color of ${type.name}`}
                      value={type.color}
                      onChange={(event) => edit(type.id, { color: event.target.value })}
                    />
                  </td>
                  <td>
                    <InlineEdit
                      label={`Name of ${type.name}`}
                      value={type.name}
                      onSave={(name) => edit(type.id, { name })}
                    />
                  </td>
                  <td>
                    <InlineEdit
                      label={`Code of ${type.name}`}
                      value={type.code}
                      onSave={(code) => edit(type.id, { code })}
                    />
                  </td>
                  <td>
                    <select
                      aria-label={`Kind of ${type.name}`}
                      value={type.role}
                      onChange={(event) => edit(type.id, { role: event.target.value as NoteType["role"] })}
                    >
                      {ROLES.map(([role, label]) => (
                        <option key={role} value={role}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <select
                      aria-label={`Merge ${type.name} into`}
                      value=""
                      onChange={(event) =>
                        event.target.value && merge.mutate({ id: type.id, into: Number(event.target.value) })
                      }
                    >
                      <option value="">Into…</option>
                      {types.data
                        .filter((other) => other.id !== type.id)
                        .map((other) => (
                          <option key={other.id} value={other.id}>
                            {other.name}
                          </option>
                        ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <form className="add-row" onSubmit={onAdd} aria-label="New note type">
            <label>
              Name
              <input
                required
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
            </label>
            <label>
              Code
              <input
                required
                value={draft.code}
                placeholder="g"
                onChange={(event) => setDraft({ ...draft, code: event.target.value })}
              />
            </label>
            <label>
              Color
              <input
                type="color"
                value={draft.color}
                onChange={(event) => setDraft({ ...draft, color: event.target.value })}
              />
            </label>
            <button type="submit">Add note type</button>
          </form>
          <p className="quiet">
            Merging gives a type&rsquo;s notes to another type and removes it. A type&rsquo;s code is the
            prefix the old commentary files use in note ids.
          </p>
        </>
      )}
    </VersionShell>
  );
}
