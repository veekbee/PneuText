// Export: the monograph, as a LaTeX project built from blank pages and the notes, and
// backups of the whole library. An edition (export profile) chooses which notes go in.
import { type FormEvent, useState } from "react";

import { api, type BackupResult, type MonographResult, type Profile, type ProfileInput } from "../api/client";
import { useChange, useMonographDefaults, useNoteTypes, useProfiles } from "../api/queries";
import { Loading, VersionShell } from "../shell/VersionShell";

function describe(profile: Profile, typeNames: Map<number, string>): string {
  const levels = profile.levels.includes(2) ? "every reading level" : "first-reading notes only";
  const statuses = profile.statuses.includes("draft") ? "drafts included" : "ready notes only";
  const types =
    profile.type_ids === null
      ? "every note type"
      : profile.type_ids.map((id) => typeNames.get(id) ?? "?").join(", ");
  return `${types}; ${levels}; ${statuses}`;
}

function ProfileEditor({
  profile,
  onSave,
  onDelete,
}: {
  profile: Profile | null;
  onSave: (input: ProfileInput) => void;
  onDelete: (() => void) | null;
}) {
  const types = useNoteTypes();
  const [draft, setDraft] = useState<ProfileInput>(
    profile
      ? { name: profile.name, type_ids: profile.type_ids, levels: profile.levels, statuses: profile.statuses }
      : { name: "", type_ids: null, levels: [1], statuses: ["ready"] },
  );
  const allTypes = (types.data ?? []).map((type) => type.id);
  const chosen = draft.type_ids ?? allTypes;

  function toggleType(id: number): void {
    const next = chosen.includes(id) ? chosen.filter((item) => item !== id) : [...chosen, id];
    // Every type chosen is stored as "all", so types added later are included too.
    setDraft({ ...draft, type_ids: next.length === allTypes.length ? null : next });
  }

  function onSubmit(event: FormEvent): void {
    event.preventDefault();
    onSave(draft);
  }

  return (
    <form className="profile-editor" aria-label={profile ? `Edit ${profile.name}` : "New edition"} onSubmit={onSubmit}>
      <label>
        Name
        <input required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
      </label>
      <fieldset>
        <legend>Reading levels</legend>
        <label>
          <input
            type="checkbox"
            checked={(draft.levels ?? []).includes(2)}
            onChange={(event) => setDraft({ ...draft, levels: event.target.checked ? [1, 2] : [1] })}
          />
          Include notes for readers who know the whole book (each is marked)
        </label>
      </fieldset>
      <fieldset>
        <legend>Status</legend>
        <label>
          <input
            type="checkbox"
            checked={(draft.statuses ?? []).includes("draft")}
            onChange={(event) =>
              setDraft({ ...draft, statuses: event.target.checked ? ["draft", "ready"] : ["ready"] })
            }
          />
          Include drafts as well as ready notes
        </label>
      </fieldset>
      <fieldset>
        <legend>Note types</legend>
        {(types.data ?? []).map((type) => (
          <label key={type.id}>
            <input type="checkbox" checked={chosen.includes(type.id)} onChange={() => toggleType(type.id)} />
            {type.name}
          </label>
        ))}
      </fieldset>
      <div className="editor-actions">
        <button type="submit">{profile ? "Save edition" : "Add edition"}</button>
        {onDelete && (
          <button type="button" className="quiet-button" onClick={onDelete}>
            Delete edition
          </button>
        )}
      </div>
    </form>
  );
}

function Result({ result }: { result: MonographResult }) {
  return (
    <section className="notice" role="status" aria-label="Export result">
      <p>
        Wrote {result.files.length} files to <code>{result.folder}</code>: {result.notes}{" "}
        {result.notes === 1 ? "note" : "notes"} on {result.pages} {result.pages === 1 ? "page" : "pages"}.
      </p>
      <p className="build">{result.pdf ? `PDF: ${result.pdf}` : result.build.split("\n")[0]}</p>
      {!result.pdf && result.build.includes("\n") && <pre>{result.build.split("\n").slice(1).join("\n")}</pre>}
      {result.warnings.length > 0 && (
        <ul className="problems">
          {result.warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ExportView({ versionId }: { versionId: number }) {
  const profiles = useProfiles();
  const types = useNoteTypes();
  const [chosen, setChosen] = useState<number | null>(null);
  const [editing, setEditing] = useState<"edit" | "new" | null>(null);
  const [folder, setFolder] = useState("");
  const [buildPdf, setBuildPdf] = useState(true);
  const [backupFolder, setBackupFolder] = useState("");
  const [backup, setBackup] = useState<BackupResult | null>(null);

  const profileId = chosen ?? profiles.data?.[0]?.id ?? null;
  const profile = profiles.data?.find((item) => item.id === profileId) ?? null;
  const defaults = useMonographDefaults(versionId, profileId);
  const typeNames = new Map((types.data ?? []).map((type) => [type.id, type.name]));

  const exportMonograph = useChange(() => api.exportMonograph(versionId, profileId as number, folder, buildPdf));
  const saveProfile = useChange(({ id, input }: { id: number | null; input: ProfileInput }) =>
    id === null ? api.createProfile(input) : api.updateProfile(id, input),
  );
  const deleteProfile = useChange((id: number) => api.deleteProfile(id));
  const exportBackup = useChange((includeText: boolean) => api.exportBackup(backupFolder, includeText));
  const error = exportMonograph.error ?? saveProfile.error ?? deleteProfile.error ?? exportBackup.error;

  return (
    <VersionShell versionId={versionId} view="export" title="Export">
      {error && (
        <div role="alert" className="notice">
          <p>{error.message}</p>
        </div>
      )}
      {profiles.data === undefined ? (
        <Loading error={profiles.error} />
      ) : (
        <>
          <section aria-labelledby="monograph-title">
            <h2 id="monograph-title">Monograph</h2>
            <p className="quiet">
              A LaTeX project: each annotated page drawn blank with numbered highlights, then its
              notes; a glossary, indexes and a list of figures. It contains none of the book&rsquo;s
              text.
            </p>
            <div className="add-row">
              <label>
                Edition
                <select
                  value={profileId ?? ""}
                  onChange={(event) => {
                    setChosen(Number(event.target.value));
                    setEditing(null);
                  }}
                >
                  {profiles.data.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className="quiet-button" onClick={() => setEditing(editing === "edit" ? null : "edit")}>
                Change this edition
              </button>
              <button type="button" className="quiet-button" onClick={() => setEditing(editing === "new" ? null : "new")}>
                New edition
              </button>
            </div>
            {profile && <p className="quiet">Includes {describe(profile, typeNames)}.</p>}
            {editing !== null && (
              <ProfileEditor
                key={editing === "edit" ? `edit-${profileId}` : "new"}
                profile={editing === "edit" ? profile : null}
                onSave={(input) =>
                  saveProfile.mutate(
                    { id: editing === "edit" ? profileId : null, input },
                    {
                      onSuccess: (saved) => {
                        setChosen(saved.id);
                        setEditing(null);
                      },
                    },
                  )
                }
                onDelete={
                  editing === "edit" && profile && profiles.data.length > 1
                    ? () =>
                        deleteProfile.mutate(profile.id, {
                          onSuccess: () => {
                            setChosen(null);
                            setEditing(null);
                          },
                        })
                    : null
                }
              />
            )}
            <div className="form export-form">
              <label>
                Folder to write to
                <input
                  value={folder}
                  placeholder={defaults.data?.folder ?? ""}
                  onChange={(event) => setFolder(event.target.value)}
                />
              </label>
              <label className="check">
                <input type="checkbox" checked={buildPdf} onChange={(event) => setBuildPdf(event.target.checked)} />
                Build the PDF as well
                <span className="quiet">
                  {defaults.data === undefined
                    ? ""
                    : defaults.data.pdf_builder
                      ? ` (with ${defaults.data.pdf_builder})`
                      : " (no LaTeX is installed here, so only the source will be written)"}
                </span>
              </label>
              <button
                type="button"
                disabled={profileId === null || exportMonograph.isPending}
                onClick={() => exportMonograph.mutate(undefined)}
              >
                {exportMonograph.isPending ? "Exporting…" : "Export the monograph"}
              </button>
            </div>
            {exportMonograph.data && <Result result={exportMonograph.data} />}
          </section>

          <section aria-labelledby="backup-title">
            <h2 id="backup-title">Backup</h2>
            <p className="quiet">The whole library as one JSON file, with its figures.</p>
            <div className="form export-form">
              <label>
                Folder to write to
                <input
                  value={backupFolder}
                  placeholder="A folder inside the library"
                  onChange={(event) => setBackupFolder(event.target.value)}
                />
              </label>
              <div className="editor-actions">
                <button
                  type="button"
                  disabled={exportBackup.isPending}
                  onClick={() => exportBackup.mutate(false, { onSuccess: setBackup })}
                >
                  Back up without the text
                </button>
                <button
                  type="button"
                  className="quiet-button"
                  disabled={exportBackup.isPending}
                  onClick={() => exportBackup.mutate(true, { onSuccess: setBackup })}
                >
                  Back up everything (private: includes the text)
                </button>
              </div>
            </div>
            {backup && (
              <section className="notice" role="status" aria-label="Backup result">
                <p>
                  Wrote {backup.files.length} files to <code>{backup.folder}</code>.{" "}
                  {backup.includes_text
                    ? "This backup contains the text of the book. Keep it private."
                    : "This backup contains no text of the book."}
                </p>
              </section>
            )}
          </section>
        </>
      )}
    </VersionShell>
  );
}
