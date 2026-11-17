// The reader's two controls: a reading-level switch and a toggle per note type.
// Plain props in, changes out, so the static web edition can reuse it.
import type { CSSProperties } from "react";

import type { NoteType } from "../api/client";
import type { ReadingLevel } from "../lib/filters";

interface NoteFiltersProps {
  level: ReadingLevel;
  hiddenTypes: number[];
  types: NoteType[];
  onLevel: (level: ReadingLevel) => void;
  onHiddenTypes: (hidden: number[]) => void;
}

export function NoteFilters({ level, hiddenTypes, types, onLevel, onHiddenTypes }: NoteFiltersProps) {
  function toggle(typeId: number): void {
    onHiddenTypes(
      hiddenTypes.includes(typeId)
        ? hiddenTypes.filter((id) => id !== typeId)
        : [...hiddenTypes, typeId],
    );
  }
  return (
    <div className="note-filters">
      <div className="segmented" role="group" aria-label="Reading level">
        <button
          type="button"
          aria-pressed={level === "first"}
          title="Hide notes that assume you know the whole book"
          onClick={() => onLevel("first")}
        >
          First reading
        </button>
        <button
          type="button"
          aria-pressed={level === "all"}
          title="Show every note"
          onClick={() => onLevel("all")}
        >
          Have read
        </button>
      </div>
      <div className="type-toggles" role="group" aria-label="Note types">
        {types.map((type) => (
          <button
            key={type.id}
            type="button"
            className="type-toggle"
            aria-pressed={!hiddenTypes.includes(type.id)}
            title={`${hiddenTypes.includes(type.id) ? "Show" : "Hide"} ${type.name} notes`}
            style={{ "--type-color": type.color } as CSSProperties}
            onClick={() => toggle(type.id)}
          >
            {type.name}
          </button>
        ))}
      </div>
    </div>
  );
}
