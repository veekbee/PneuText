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
  renderNoteBody: (bodyMd: string) =>
    post<{ body: NoteNode }>("/api/notes/render", { body_md: bodyMd }),
};
