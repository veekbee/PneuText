// The thin fetch client. Everything the front end asks of the server goes through here,
// typed by schema.d.ts, which is generated from the server's OpenAPI schema.
import type { components } from "./schema";

type Schemas = components["schemas"];
export type LibraryInfo = Schemas["LibraryOut"];
export type VersionSummary = Schemas["VersionSummaryOut"];
export type Version = Schemas["VersionOut"];
export type Division = Schemas["DivisionOut"];
export type PageText = Schemas["PageTextOut"];
export type TextLine = Schemas["TextLineOut"];
export type PageShape = Schemas["PageShapeOut"];
export type ShapeLine = Schemas["ShapeLineOut"];
export type CorpusImportInput = Schemas["CorpusImportIn"];
export type CorpusImportPreview = Schemas["CorpusImportPreviewOut"];
export type CorpusImportResult = Schemas["CorpusImportOut"];
export type ImportProblem = Schemas["ImportProblemOut"];
export type NoteType = Schemas["NoteTypeOut"];
export type Note = Schemas["NoteOut"];
export type NoteNode = Schemas["NoteNode"];
export type NoteCreateInput = Schemas["NoteCreateIn"];
export type NoteUpdateInput = Schemas["NoteUpdateIn"];
export type SpanInput = Schemas["SpanIn"];
export type Highlight = Schemas["ShapeHighlightOut"];
export type Backlink = Schemas["BacklinkOut"];
export type PageLinks = Schemas["PageLinksOut"];
export type PassageLink = Schemas["PassageLinkOut"];
export type SearchResults = Schemas["SearchOut"];
export type Figure = Schemas["FigureOut"];
export type MentionMark = Schemas["MentionMarkOut"];
export type Category = Schemas["CategoryOut"];
export type Entity = Schemas["EntityOut"];
export type MentionInput = Schemas["MentionIn"];
export type TimeValueInput = Schemas["TimeValueIn"];
export type ChronologyRow = Schemas["ChronologyRowOut"];
export type NoteSummary = Schemas["NoteSummaryOut"];
export type TodoList = Schemas["TodoListOut"];
export type NoteTypeInput = Schemas["NoteTypeIn"];
export type NoteTypeUpdate = Schemas["NoteTypeUpdateIn"];
export type FigureUpdate = Schemas["FigureUpdateIn"];
export type LegacyImportInput = Schemas["LegacyImportIn"];
export type LegacyReport = Schemas["LegacyReportOut"];
export type ReportItem = Schemas["ReportItemOut"];

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // Not JSON; fall through to the generic message.
  }
  return `The server answered with an error (${response.status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "PneuText's server is not responding. Is it still running?");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function send<T>(method: string, path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

function post<T>(path: string, body: unknown): Promise<T> {
  return send<T>("POST", path, body);
}

export const api = {
  getLibrary: () => request<LibraryInfo>("/api/library"),
  listVersions: () => request<VersionSummary[]>("/api/versions"),
  getVersion: (versionId: number) => request<Version>(`/api/versions/${versionId}`),
  getPageText: (versionId: number, page: number) =>
    request<PageText>(`/api/versions/${versionId}/pages/${page}/text`),
  getPageShape: (versionId: number, page: number) =>
    request<PageShape>(`/api/versions/${versionId}/pages/${page}/shape`),
  previewCorpusImport: (input: CorpusImportInput) =>
    post<CorpusImportPreview>("/api/imports/corpus/preview", input),
  importCorpus: (input: CorpusImportInput) =>
    post<CorpusImportResult>("/api/imports/corpus", input),
  previewCommentaryImport: (versionId: number, input: LegacyImportInput) =>
    post<LegacyReport>(`/api/versions/${versionId}/imports/commentary/preview`, input),
  importCommentary: (versionId: number, input: LegacyImportInput) =>
    post<LegacyReport>(`/api/versions/${versionId}/imports/commentary`, input),
  listNoteTypes: () => request<NoteType[]>("/api/note-types"),
  listPageNotes: (versionId: number, page: number) =>
    request<Note[]>(`/api/versions/${versionId}/pages/${page}/notes`),
  createNote: (versionId: number, input: NoteCreateInput) =>
    post<Note>(`/api/versions/${versionId}/notes`, input),
  updateNote: (noteId: number, input: NoteUpdateInput) =>
    send<Note>("PATCH", `/api/notes/${noteId}`, input),
  deleteNote: (noteId: number) => request<undefined>(`/api/notes/${noteId}`, { method: "DELETE" }),
  renderNoteBody: (bodyMd: string, versionId: number | null, noteId: number | null = null) =>
    post<{ body: NoteNode }>("/api/notes/render", {
      body_md: bodyMd,
      version_id: versionId,
      note_id: noteId,
    }),
  listPageLinks: (versionId: number, page: number) =>
    request<PageLinks>(`/api/versions/${versionId}/pages/${page}/links`),
  createPassageLink: (versionId: number, source: SpanInput, target: SpanInput) =>
    post<{ id: number }>(`/api/versions/${versionId}/links`, { source, target }),
  deletePassageLink: (linkId: number) =>
    request<undefined>(`/api/links/${linkId}`, { method: "DELETE" }),
  search: (versionId: number, query: string, corpus: boolean) =>
    request<SearchResults>(
      `/api/versions/${versionId}/search?q=${encodeURIComponent(query)}&corpus=${corpus}`,
    ),
  listFigures: () => request<Figure[]>("/api/figures"),
  createFigure: (label: string, caption: string, credit: string) =>
    post<Figure>("/api/figures", { label, caption, credit }),
  updateFigure: (figureId: number, changes: FigureUpdate) =>
    send<Figure>("PATCH", `/api/figures/${figureId}`, changes),
  deleteFigure: (figureId: number) =>
    request<undefined>(`/api/figures/${figureId}`, { method: "DELETE" }),
  uploadFigureImage: (figureId: number, file: Blob) =>
    request<Figure>(`/api/figures/${figureId}/image`, {
      method: "PUT",
      headers: { "content-type": file.type || "application/octet-stream" },
      body: file,
    }),

  // Entities and narrative time
  listCategories: () => request<Category[]>("/api/entity-categories"),
  createCategory: (name: string) => post<Category>("/api/entity-categories", { name }),
  updateCategory: (categoryId: number, changes: { name?: string; color?: string }) =>
    send<Category>("PATCH", `/api/entity-categories/${categoryId}`, changes),
  mergeCategory: (categoryId: number, intoId: number) =>
    post<undefined>(`/api/entity-categories/${categoryId}/merge`, { into_id: intoId }),
  listEntities: (versionId: number, categoryId?: number, starting?: string) => {
    const params = new URLSearchParams();
    if (categoryId !== undefined) params.set("category_id", String(categoryId));
    if (starting) params.set("starting", starting);
    const query = params.toString();
    return request<Entity[]>(`/api/versions/${versionId}/entities${query ? `?${query}` : ""}`);
  },
  updateEntity: (entityId: number, changes: { name?: string; value?: string }) =>
    send<undefined>("PATCH", `/api/entities/${entityId}`, changes),
  mergeEntity: (entityId: number, intoId: number) =>
    post<undefined>(`/api/entities/${entityId}/merge`, { into_id: intoId }),
  createMention: (versionId: number, input: MentionInput) =>
    post<{ id: number }>(`/api/versions/${versionId}/mentions`, input),
  deleteMention: (mentionId: number) =>
    request<undefined>(`/api/mentions/${mentionId}`, { method: "DELETE" }),
  setTime: (mentionId: number, value: TimeValueInput) =>
    send<undefined>("PUT", `/api/mentions/${mentionId}/time`, value),
  clearTime: (mentionId: number) =>
    request<undefined>(`/api/mentions/${mentionId}/time`, { method: "DELETE" }),
  getChronology: (versionId: number) =>
    request<ChronologyRow[]>(`/api/versions/${versionId}/chronology`),

  // Review
  listNotes: (versionId: number, filters: Record<string, string | number | null>) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== null && value !== "") params.set(key, String(value));
    }
    const query = params.toString();
    return request<NoteSummary[]>(`/api/versions/${versionId}/notes${query ? `?${query}` : ""}`);
  },
  setNotesStatus: (versionId: number, noteIds: number[], status: "draft" | "ready") =>
    post<{ changed: number }>(`/api/versions/${versionId}/notes/status`, {
      note_ids: noteIds,
      status,
    }),
  listTags: () => request<string[]>("/api/tags"),
  getTodoList: (versionId: number) => request<TodoList>(`/api/versions/${versionId}/todo`),

  // Note types
  createNoteType: (input: NoteTypeInput) => post<NoteType>("/api/note-types", input),
  updateNoteType: (typeId: number, changes: NoteTypeUpdate) =>
    send<NoteType>("PATCH", `/api/note-types/${typeId}`, changes),
  mergeNoteType: (typeId: number, intoId: number) =>
    post<undefined>(`/api/note-types/${typeId}/merge`, { into_id: intoId }),
};

/** Where a figure's image is served from (the local library, never the network). */
export function figureFileUrl(label: string): string {
  return `/api/figures/${encodeURIComponent(label)}/file`;
}

/** Mentions and time points as a JSON file, for later map and timeline tools. */
export function entitiesExportUrl(versionId: number): string {
  return `/api/versions/${versionId}/entities/export`;
}
