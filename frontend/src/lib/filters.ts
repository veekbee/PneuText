// Which notes a reader sees. The reader, not the author, chooses: a reading level, and
// a toggle per note type. Shared by the app and (later) the static web edition.

export type ReadingLevel = "first" | "all";

export interface NoteFilter {
  level: ReadingLevel;
  hiddenTypes: number[];
  /** Applied in the app only; a reader of an edition sees what was exported. */
  status?: "draft" | "ready" | null;
}

interface Filterable {
  type_id: number;
  level: number;
  status?: string;
}

/** First reading hides every level 2 note; a hidden type hides its notes. */
export function isVisible(note: Filterable, filter: NoteFilter): boolean {
  if (filter.level === "first" && note.level > 1) return false;
  if (filter.hiddenTypes.includes(note.type_id)) return false;
  if (filter.status != null && note.status !== undefined && note.status !== filter.status) {
    return false;
  }
  return true;
}
