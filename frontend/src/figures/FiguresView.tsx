// Figures: upload images, edit label, caption and credit, see where each is used, and
// spot the unused ones.
import { type FormEvent, useState } from "react";

import { api, type Figure, figureFileUrl, type FigureUpdate } from "../api/client";
import { useChange, useFigures } from "../api/queries";
import { pagePath } from "../lib/route";
import { Link } from "../router";
import { InlineEdit } from "../shell/InlineEdit";
import { Loading, VersionShell } from "../shell/VersionShell";

interface Actions {
  update: (input: { id: number; changes: FigureUpdate }) => void;
  upload: (input: { id: number; file: Blob }) => void;
  remove: (id: number) => void;
}

function FigureCard({ figure, actions }: { figure: Figure; actions: Actions }) {
  const [confirming, setConfirming] = useState(false);
  const edit = (changes: FigureUpdate): void => actions.update({ id: figure.id, changes });
  return (
    <li className="figure-card" aria-label={`Figure ${figure.label}`}>
      <div className="figure-image">
        {figure.has_file ? (
          // The file name changes when the image does, which keeps the picture fresh.
          <img src={`${figureFileUrl(figure.label)}?v=${encodeURIComponent(figure.file)}`} alt={figure.caption || figure.label} />
        ) : (
          <span className="quiet">No image yet</span>
        )}
        <label className="upload">
          {figure.has_file ? "Replace image" : "Choose image"}
          <input
            type="file"
            accept="image/*"
            aria-label={`Image for ${figure.label}`}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) actions.upload({ id: figure.id, file });
              event.target.value = "";
            }}
          />
        </label>
      </div>
      <div className="figure-fields">
        <label>
          Label
          <InlineEdit label={`Label of ${figure.label}`} value={figure.label} onSave={(label) => edit({ label })} />
        </label>
        <label>
          Caption
          <InlineEdit
            label={`Caption of ${figure.label}`}
            value={figure.caption}
            onSave={(caption) => edit({ caption })}
          />
        </label>
        <label>
          Credit
          <InlineEdit
            label={`Credit of ${figure.label}`}
            value={figure.credit}
            onSave={(credit) => edit({ credit })}
          />
        </label>
        <div className="figure-uses">
          {figure.uses.length === 0 ? (
            <span className="badge unused">Unused</span>
          ) : (
            <>
              <span className="quiet">Used in </span>
              {figure.uses.map((use, index) =>
                use.page === null ? null : (
                  <Link key={index} to={pagePath(use.version_id, use.page, use.line_no)}>
                    p. {use.page}
                    {use.placed ? "" : " (cited)"}
                  </Link>
                ),
              )}
            </>
          )}
        </div>
        {confirming ? (
          <button type="button" className="danger-button" onClick={() => actions.remove(figure.id)}>
            Really delete {figure.label}
          </button>
        ) : (
          <button type="button" className="quiet-button" onClick={() => setConfirming(true)}>
            Delete
          </button>
        )}
      </div>
    </li>
  );
}

export function FiguresView({ versionId }: { versionId: number }) {
  const figures = useFigures();
  const [draft, setDraft] = useState({ label: "", caption: "", credit: "" });
  const create = useChange((input: typeof draft) =>
    api.createFigure(input.label, input.caption, input.credit),
  );
  const update = useChange(({ id, changes }: { id: number; changes: FigureUpdate }) =>
    api.updateFigure(id, changes),
  );
  const upload = useChange(({ id, file }: { id: number; file: Blob }) =>
    api.uploadFigureImage(id, file),
  );
  const remove = useChange((id: number) => api.deleteFigure(id));
  const error = create.error ?? update.error ?? upload.error ?? remove.error;

  function onAdd(event: FormEvent): void {
    event.preventDefault();
    create.mutate(draft, { onSuccess: () => setDraft({ label: "", caption: "", credit: "" }) });
  }

  return (
    <VersionShell versionId={versionId} view="figures" title="Figures">
      {error && (
        <div role="alert" className="notice">
          <p>{error.message}</p>
        </div>
      )}
      {figures.data === undefined ? (
        <Loading error={figures.error} />
      ) : (
        <>
          {figures.data.length === 0 && <p className="quiet">No figures yet.</p>}
          <ul className="figure-list">
            {figures.data.map((figure) => (
              <FigureCard
                key={figure.id}
                figure={figure}
                actions={{ update: update.mutate, upload: upload.mutate, remove: remove.mutate }}
              />
            ))}
          </ul>
          <form className="add-row" onSubmit={onAdd} aria-label="New figure">
            <label>
              Label
              <input
                required
                value={draft.label}
                placeholder="tang"
                onChange={(event) => setDraft({ ...draft, label: event.target.value })}
              />
            </label>
            <label>
              Caption
              <input
                value={draft.caption}
                onChange={(event) => setDraft({ ...draft, caption: event.target.value })}
              />
            </label>
            <label>
              Credit
              <input
                value={draft.credit}
                onChange={(event) => setDraft({ ...draft, credit: event.target.value })}
              />
            </label>
            <button type="submit">Add figure</button>
          </form>
        </>
      )}
    </VersionShell>
  );
}
