// The value of a time mention: an absolute date at any precision, or an offset from
// another time, plus an optional label that later times can count from.
import type { TimeValueInput } from "../api/client";

export type TimeDraft = Omit<TimeValueInput, "kind"> & { kind: "absolute" | "offset" | "" };

export const NO_TIME: TimeDraft = {
  kind: "",
  at: "",
  offset: "",
  relative_to_label: "",
  label: "",
  remark: "",
};

/** The draft as the server wants it, or null when no value is being given. */
export function toTimeValue(draft: TimeDraft): TimeValueInput | null {
  if (draft.kind === "") return null;
  return {
    kind: draft.kind,
    at: draft.kind === "absolute" ? (draft.at ?? "") : null,
    offset: draft.kind === "offset" ? (draft.offset ?? "") : null,
    relative_to_label: draft.kind === "offset" ? draft.relative_to_label || null : null,
    label: draft.label || null,
    remark: draft.remark ?? "",
  };
}

interface TimeFieldsProps {
  draft: TimeDraft;
  /** Labels of other times, which an offset can count from. */
  labels: string[];
  allowNone: boolean;
  onChange: (draft: TimeDraft) => void;
}

export function TimeFields({ draft, labels, allowNone, onChange }: TimeFieldsProps) {
  const set = (change: Partial<TimeDraft>): void => onChange({ ...draft, ...change });
  return (
    <div className="time-fields">
      <label>
        Kind
        <select
          value={draft.kind}
          onChange={(event) => set({ kind: event.target.value as TimeDraft["kind"] })}
        >
          {allowNone && <option value="">No value yet</option>}
          <option value="absolute">A date</option>
          <option value="offset">Time after another</option>
        </select>
      </label>
      {draft.kind === "absolute" && (
        <label>
          Date
          <input
            value={draft.at ?? ""}
            placeholder="1871, 1871-10, 1871-10-28, 1871-10-28T06:30"
            onChange={(event) => set({ at: event.target.value })}
          />
        </label>
      )}
      {draft.kind === "offset" && (
        <>
          <label>
            Offset
            <input
              value={draft.offset ?? ""}
              placeholder="P5D, P3W, P1Y2M, PT6H"
              onChange={(event) => set({ offset: event.target.value })}
            />
          </label>
          <label>
            Counts from
            <select
              value={draft.relative_to_label ?? ""}
              onChange={(event) => set({ relative_to_label: event.target.value })}
            >
              <option value="">The time before it</option>
              {labels.map((label) => (
                <option key={label} value={label}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      {draft.kind !== "" && (
        <>
          <label>
            Label
            <input
              value={draft.label ?? ""}
              placeholder="expedition-start"
              onChange={(event) => set({ label: event.target.value })}
            />
          </label>
          <label>
            Remark
            <input
              value={draft.remark ?? ""}
              placeholder="about a week; early autumn"
              onChange={(event) => set({ remark: event.target.value })}
            />
          </label>
        </>
      )}
    </div>
  );
}
