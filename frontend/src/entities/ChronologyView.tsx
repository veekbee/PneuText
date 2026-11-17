// Every time point in reading order: its page, its value, the narrative date it resolves
// to, and the time elapsed since each labeled point. Editing one value updates the rest.
import { type FormEvent, useState } from "react";

import { api, type ChronologyRow, type TimeValueInput } from "../api/client";
import { useChange, useChronology } from "../api/queries";
import { pagePath } from "../lib/route";
import { Link } from "../router";
import { Loading, VersionShell } from "../shell/VersionShell";
import { type TimeDraft, TimeFields, toTimeValue } from "./TimeFields";

function draftOf(row: ChronologyRow): TimeDraft {
  return {
    kind: row.kind ?? "",
    at: row.at ?? "",
    offset: row.offset ?? "",
    relative_to_label: row.relative_to_label ?? "",
    label: row.label ?? "",
    remark: row.remark,
  };
}

function Row({
  versionId,
  row,
  labels,
  onSave,
  onClear,
}: {
  versionId: number;
  row: ChronologyRow;
  labels: string[];
  onSave: (value: TimeValueInput) => void;
  onClear: () => void;
}) {
  const [draft, setDraft] = useState<TimeDraft>(draftOf(row));
  const place = row.page === null ? "" : `${row.page}${row.line_no === null ? "" : `.${row.line_no}`}`;

  function onSubmit(event: FormEvent): void {
    event.preventDefault();
    const value = toTimeValue(draft);
    if (value === null) onClear();
    else onSave(value);
  }

  return (
    <tr data-mention={row.mention_id}>
      <td>
        {row.page === null ? "" : <Link to={pagePath(versionId, row.page, row.line_no)}>{place}</Link>}
      </td>
      <td>
        <form onSubmit={onSubmit} aria-label={`Time at ${place}`} className="time-form">
          <TimeFields
            draft={draft}
            labels={labels.filter((label) => label !== row.label)}
            allowNone
            onChange={setDraft}
          />
          <button type="submit" className="quiet-button">
            Save
          </button>
        </form>
      </td>
      <td className="resolved">
        {row.date_words ?? (row.elapsed_words ? `${row.elapsed_words} in` : "")}
        {row.problem && <span className="quiet">{row.problem}</span>}
      </td>
      <td>
        {row.since.map((item) => (
          <div key={item.label}>
            {item.words} <span className="quiet">since {item.label}</span>
          </div>
        ))}
      </td>
    </tr>
  );
}

export function ChronologyView({ versionId }: { versionId: number }) {
  const chronology = useChronology(versionId);
  const save = useChange(({ id, value }: { id: number; value: TimeValueInput }) =>
    api.setTime(id, value),
  );
  const clear = useChange((id: number) => api.clearTime(id));
  const error = save.error ?? clear.error;
  const rows = chronology.data;
  const labels = (rows ?? []).flatMap((row) => (row.label ? [row.label] : []));

  return (
    <VersionShell versionId={versionId} view="chronology" title="Chronology">
      {error && (
        <div role="alert" className="notice">
          <p>{error.message}</p>
        </div>
      )}
      {rows === undefined ? (
        <Loading error={chronology.error} />
      ) : rows.length === 0 ? (
        <p className="quiet">
          No times are tagged yet. Select words on a page, choose Tag entity, and pick the time
          category.
        </p>
      ) : (
        <table className="data-table chronology">
          <thead>
            <tr>
              <th>Place</th>
              <th>Value</th>
              <th>Resolves to</th>
              <th>Elapsed</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <Row
                // A row starts afresh when its stored value changes.
                key={`${row.mention_id}:${row.kind}:${row.at}:${row.offset}:${row.label}:${row.relative_to_label}:${row.remark}`}
                versionId={versionId}
                row={row}
                labels={labels}
                onSave={(value) => save.mutate({ id: row.mention_id, value })}
                onClear={() => clear.mutate(row.mention_id)}
              />
            ))}
          </tbody>
        </table>
      )}
    </VersionShell>
  );
}
