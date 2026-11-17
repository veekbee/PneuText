// Tag the selection: assign it to an existing entity or a new one, chosen by category
// with type-ahead; or, in the time category, record what time it denotes.
import { type FormEvent, useState } from "react";

import type { Category, MentionInput } from "../api/client";
import { useChronology, useEntities } from "../api/queries";
import { NO_TIME, type TimeDraft, TimeFields, toTimeValue } from "./TimeFields";

interface TagEntityFormProps {
  versionId: number;
  /** The words selected, which name a new entity unless another name is typed. */
  words: string;
  categories: Category[];
  defaultCategory: number | null;
  saving: boolean;
  error: string | null;
  onTag: (input: Omit<MentionInput, "span">) => void;
  onCancel: () => void;
}

export function TagEntityForm(props: TagEntityFormProps) {
  const { versionId, words, categories } = props;
  const [categoryId, setCategoryId] = useState(props.defaultCategory ?? categories[0]?.id ?? 0);
  const [name, setName] = useState(words);
  const [value, setValue] = useState("");
  const [time, setTime] = useState<TimeDraft>(NO_TIME);
  const category = categories.find((item) => item.id === categoryId);
  const isTime = category?.is_time ?? false;
  // Type-ahead: entities of this category whose names start with what is typed.
  const matches = useEntities(versionId, categoryId, name.trim().slice(0, 40));
  const chronology = useChronology(versionId);
  const labels = (chronology.data ?? []).flatMap((row) => (row.label ? [row.label] : []));

  function onSubmit(event: FormEvent): void {
    event.preventDefault();
    if (isTime) {
      props.onTag({ category_id: categoryId, time: toTimeValue(time) });
      return;
    }
    const existing = (matches.data ?? []).find(
      (entity) => entity.name.toLowerCase() === name.trim().toLowerCase(),
    );
    props.onTag({
      category_id: categoryId,
      entity_id: existing?.id ?? null,
      entity_name: existing ? null : name.trim(),
      value: value.trim() || null,
    });
  }

  return (
    <form className="tag-form" aria-label="Tag entity" onSubmit={onSubmit}>
      <label>
        Category
        <select value={categoryId} onChange={(event) => setCategoryId(Number(event.target.value))}>
          {categories.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {isTime ? (
        <TimeFields draft={time} labels={labels} allowNone onChange={setTime} />
      ) : (
        <>
          <label>
            Entity
            <input
              value={name}
              list="tag-entity-names"
              autoFocus
              required
              onChange={(event) => setName(event.target.value)}
            />
            <datalist id="tag-entity-names">
              {(matches.data ?? []).map((entity) => (
                <option key={entity.id} value={entity.name} />
              ))}
            </datalist>
          </label>
          <label>
            Value
            <input
              value={value}
              placeholder="optional, such as 46"
              onChange={(event) => setValue(event.target.value)}
            />
          </label>
        </>
      )}
      {props.error !== null && (
        <p role="alert" className="editor-error">
          {props.error}
        </p>
      )}
      <div className="editor-actions">
        <button type="submit" disabled={props.saving}>
          {props.saving ? "Tagging…" : "Tag"}
        </button>
        <button type="button" className="quiet-button" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
