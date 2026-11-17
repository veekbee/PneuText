// The index: each category's entities with every page they occur on. Entries can be
// renamed, merged and given a normalized value; categories can be added, renamed,
// recolored and merged.
import { type FormEvent, useState } from "react";

import { api, type Category, type Entity, entitiesExportUrl } from "../api/client";
import { useCategories, useChange, useEntities } from "../api/queries";
import { pagePath, viewPath } from "../lib/route";
import { Link } from "../router";
import { InlineEdit } from "../shell/InlineEdit";
import { Loading, VersionShell } from "../shell/VersionShell";

function Places({ versionId, entity }: { versionId: number; entity: Entity }) {
  if (entity.places.length === 0) return <span className="quiet">not in this text</span>;
  return (
    <span className="places">
      {entity.places.map((place, index) => (
        <Link key={index} to={pagePath(versionId, place.page, place.line_no)}>
          {place.page}
        </Link>
      ))}
    </span>
  );
}

interface Actions {
  rename: (input: { id: number; name?: string; value?: string }) => void;
  merge: (input: { id: number; into: number }) => void;
  renameCategory: (input: { id: number; name?: string; color?: string }) => void;
  mergeCategory: (input: { id: number; into: number }) => void;
}

function CategorySection({
  versionId,
  category,
  categories,
  entities,
  actions,
}: {
  versionId: number;
  category: Category;
  categories: Category[];
  entities: Entity[];
  actions: Actions;
}) {
  const others = categories.filter((item) => item.id !== category.id && !item.is_time);
  return (
    <section className="category" aria-label={category.name}>
      <header className="category-head">
        <input
          type="color"
          aria-label={`Color of ${category.name}`}
          value={category.color}
          onChange={(event) => actions.renameCategory({ id: category.id, color: event.target.value })}
        />
        <InlineEdit
          label={`Name of the category ${category.name}`}
          className="inline-edit category-name"
          value={category.name}
          onSave={(name) => actions.renameCategory({ id: category.id, name })}
        />
        <span className="quiet">
          {category.is_time ? "times" : `${entities.length} ${entities.length === 1 ? "entry" : "entries"}`}
        </span>
        {!category.is_time && others.length > 0 && (
          <select
            aria-label={`Merge ${category.name} into`}
            value=""
            onChange={(event) =>
              event.target.value &&
              actions.mergeCategory({ id: category.id, into: Number(event.target.value) })
            }
          >
            <option value="">Merge into…</option>
            {others.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        )}
      </header>
      {category.is_time ? (
        <p className="quiet">
          Time mentions have dates, not entries. They are listed in the{" "}
          <Link to={viewPath(versionId, "chronology")}>chronology</Link>.
        </p>
      ) : entities.length === 0 ? (
        <p className="quiet">Nothing tagged yet.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Entry</th>
              <th>Value</th>
              <th>Pages</th>
              <th>Merge</th>
            </tr>
          </thead>
          <tbody>
            {entities.map((entity) => (
              <tr key={entity.id}>
                <td>
                  <InlineEdit
                    label={`Name of ${entity.name}`}
                    value={entity.name}
                    onSave={(name) => actions.rename({ id: entity.id, name })}
                  />
                </td>
                <td>
                  <InlineEdit
                    label={`Value of ${entity.name}`}
                    value={entity.value ?? ""}
                    placeholder="—"
                    onSave={(value) => actions.rename({ id: entity.id, value })}
                  />
                </td>
                <td>
                  <Places versionId={versionId} entity={entity} />
                </td>
                <td>
                  {entities.length > 1 && (
                    <select
                      aria-label={`Merge ${entity.name} into`}
                      value=""
                      onChange={(event) =>
                        event.target.value &&
                        actions.merge({ id: entity.id, into: Number(event.target.value) })
                      }
                    >
                      <option value="">Into…</option>
                      {entities
                        .filter((other) => other.id !== entity.id)
                        .map((other) => (
                          <option key={other.id} value={other.id}>
                            {other.name}
                          </option>
                        ))}
                    </select>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function EntitiesView({ versionId }: { versionId: number }) {
  const categories = useCategories();
  const entities = useEntities(versionId);
  const [newName, setNewName] = useState("");
  const rename = useChange(({ id, ...changes }: { id: number; name?: string; value?: string }) =>
    api.updateEntity(id, changes),
  );
  const merge = useChange(({ id, into }: { id: number; into: number }) => api.mergeEntity(id, into));
  const renameCategory = useChange(
    ({ id, ...changes }: { id: number; name?: string; color?: string }) =>
      api.updateCategory(id, changes),
  );
  const mergeCategory = useChange(({ id, into }: { id: number; into: number }) =>
    api.mergeCategory(id, into),
  );
  const addCategory = useChange((name: string) => api.createCategory(name));
  const error =
    rename.error ?? merge.error ?? renameCategory.error ?? mergeCategory.error ?? addCategory.error;

  function onAdd(event: FormEvent): void {
    event.preventDefault();
    addCategory.mutate(newName, { onSuccess: () => setNewName("") });
  }

  return (
    <VersionShell versionId={versionId} view="entities" title="Entities">
      {error && (
        <div role="alert" className="notice">
          <p>{error.message}</p>
        </div>
      )}
      {categories.data === undefined || entities.data === undefined ? (
        <Loading error={categories.error ?? entities.error} />
      ) : (
        <>
          {categories.data.map((category) => (
            <CategorySection
              key={category.id}
              versionId={versionId}
              category={category}
              categories={categories.data}
              entities={entities.data.filter((entity) => entity.category_id === category.id)}
              actions={{
                rename: rename.mutate,
                merge: merge.mutate,
                renameCategory: renameCategory.mutate,
                mergeCategory: mergeCategory.mutate,
              }}
            />
          ))}
          <form className="add-row" onSubmit={onAdd}>
            <label>
              New category
              <input value={newName} required onChange={(event) => setNewName(event.target.value)} />
            </label>
            <button type="submit">Add category</button>
          </form>
          <p>
            <a href={entitiesExportUrl(versionId)} download="entities.json">
              Download mentions and times as data
            </a>{" "}
            <span className="quiet">(JSON, for map and timeline tools; no text of the book)</span>
          </p>
        </>
      )}
    </VersionShell>
  );
}
