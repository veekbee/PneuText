import {
  keepPreviousData,
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import type { RowMark } from "../lib/selection";
import {
  api,
  type CorpusImportInput,
  type LegacyImportInput,
  type Note,
  type NoteCreateInput,
  type NoteUpdateInput,
  type PageText,
  type SpanInput,
} from "./client";

export function useLibrary() {
  return useQuery({ queryKey: ["library"], queryFn: api.getLibrary });
}

export function useVersions() {
  return useQuery({ queryKey: ["versions"], queryFn: api.listVersions });
}

export function useVersion(versionId: number) {
  return useQuery({
    queryKey: ["version", versionId],
    queryFn: () => api.getVersion(versionId),
  });
}

// Page caches are keyed by the version's edit_seq, so nothing outlives an edit to the text.
export function usePageText(
  versionId: number,
  editSeq: number | undefined,
  page: number,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["page-text", versionId, editSeq, page],
    queryFn: () => api.getPageText(versionId, page),
    enabled: enabled && editSeq !== undefined,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  });
}

// The shape projection: all that blank mode asks the server for.
export function usePageShape(
  versionId: number,
  editSeq: number | undefined,
  page: number,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["page-shape", versionId, editSeq, page],
    queryFn: () => api.getPageShape(versionId, page),
    enabled: enabled && editSeq !== undefined,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  });
}

export function usePreviewCorpusImport() {
  return useMutation({ mutationFn: (input: CorpusImportInput) => api.previewCorpusImport(input) });
}

export function useImportCorpus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CorpusImportInput) => api.importCorpus(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["versions"] }),
  });
}

// ---- Notes -----------------------------------------------------------------

export function useNoteTypes() {
  return useQuery({ queryKey: ["note-types"], queryFn: api.listNoteTypes, staleTime: Infinity });
}

export function usePageNotes(versionId: number, page: number) {
  return useQuery({
    queryKey: ["page-notes", versionId, page],
    queryFn: () => api.listPageNotes(versionId, page),
    retry: false,
  });
}

/** The server's parse of a note body, for the editor's live preview. */
export function useRenderedBody(bodyMd: string, versionId: number, enabled: boolean) {
  return useQuery({
    queryKey: ["note-render", versionId, bodyMd],
    queryFn: async () => (await api.renderNoteBody(bodyMd, versionId)).body,
    enabled,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });
}

/** Everything drawn from notes: refetch it for this version after a change. */
function invalidateNotes(queryClient: QueryClient, versionId: number) {
  return Promise.all(
    ["page-text", "page-shape", "page-notes", "page-links"].map((name) =>
      queryClient.invalidateQueries({ queryKey: [name, versionId] }),
    ),
  );
}

export interface NewNoteVariables {
  input: NoteCreateInput;
  page: number;
  editSeq: number;
  /** A temporary, negative id for the note until the server answers. */
  tempId: number;
  /** Where the new highlight falls on the lines of this page. */
  marks: RowMark[];
  start: { page: number; line_no: number | null } | null;
  end: { page: number; line_no: number | null } | null;
}

/**
 * Create a note. Its highlight and its entry in the page's list appear at once, before
 * the server confirms; if the save fails they are taken away again.
 */
export function useCreateNote(versionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ input }: NewNoteVariables) => api.createNote(versionId, input),
    onMutate: async ({ input, page, editSeq, tempId, marks, start, end }) => {
      const textKey = ["page-text", versionId, editSeq, page];
      const notesKey = ["page-notes", versionId, page];
      await Promise.all([
        queryClient.cancelQueries({ queryKey: textKey }),
        queryClient.cancelQueries({ queryKey: notesKey }),
      ]);
      const previousText = queryClient.getQueryData<PageText>(textKey);
      const previousNotes = queryClient.getQueryData<Note[]>(notesKey);
      const level = input.level ?? 1;
      if (previousText !== undefined && marks.length > 0) {
        queryClient.setQueryData<PageText>(textKey, {
          ...previousText,
          lines: previousText.lines.map((line) => {
            const added = marks
              .filter((mark) => mark.lineId === line.id)
              .map((mark) => ({
                annotation_id: tempId,
                type_id: input.type_id,
                level,
                start: mark.start,
                end: mark.end,
              }));
            return added.length === 0
              ? line
              : { ...line, highlights: [...line.highlights, ...added] };
          }),
        });
      }
      const span = input.span;
      const pending: Note = {
        id: tempId,
        version_id: versionId,
        type_id: input.type_id,
        scope: input.scope ?? "span",
        level,
        status: input.status ?? "draft",
        body_md: input.body_md ?? "",
        body: { type: "document", children: [] },
        tags: [],
        legacy_id: null,
        created_at: "",
        updated_at: "",
        anchor: {
          start_segment_id: span?.start_segment_id ?? 0,
          start_offset: span?.start_offset ?? 0,
          end_segment_id: span?.end_segment_id ?? 0,
          end_offset: span?.end_offset ?? 0,
          status: "ok",
        },
        start,
        end,
        backlinks: [],
      };
      queryClient.setQueryData<Note[]>(notesKey, [...(previousNotes ?? []), pending]);
      return { textKey, notesKey, previousText, previousNotes };
    },
    onError: (_error, _variables, context) => {
      if (context === undefined) return;
      queryClient.setQueryData(context.textKey, context.previousText);
      queryClient.setQueryData(context.notesKey, context.previousNotes);
    },
    onSettled: () => invalidateNotes(queryClient, versionId),
  });
}

export function useUpdateNote(versionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, changes }: { noteId: number; changes: NoteUpdateInput }) =>
      api.updateNote(noteId, changes),
    onSuccess: () => invalidateNotes(queryClient, versionId),
  });
}

export function useDeleteNote(versionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noteId: number) => api.deleteNote(noteId),
    onSuccess: () => invalidateNotes(queryClient, versionId),
  });
}

// ---- Legacy commentary import -------------------------------------------------

export function usePreviewCommentaryImport(versionId: number) {
  return useMutation({
    mutationFn: (input: LegacyImportInput) => api.previewCommentaryImport(versionId, input),
  });
}

export function useImportCommentary(versionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: LegacyImportInput) => api.importCommentary(versionId, input),
    onSuccess: () => invalidateNotes(queryClient, versionId),
  });
}

// ---- Links, search, figures ---------------------------------------------------

/** What points at a page: notes that refer to it, and passage links that touch it. */
export function usePageLinks(versionId: number, page: number) {
  return useQuery({
    queryKey: ["page-links", versionId, page],
    queryFn: () => api.listPageLinks(versionId, page),
    retry: false,
  });
}

export function useCreatePassageLink(versionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ source, target }: { source: SpanInput; target: SpanInput }) =>
      api.createPassageLink(versionId, source, target),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["page-links", versionId] }),
  });
}

export function useDeletePassageLink(versionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: number) => api.deletePassageLink(linkId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["page-links", versionId] }),
  });
}

/** Search one text. The corpus is searched only in text mode. */
export function useSearch(versionId: number, query: string, corpus: boolean) {
  return useQuery({
    queryKey: ["search", versionId, query, corpus],
    queryFn: () => api.search(versionId, query, corpus),
    enabled: query.trim() !== "",
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
}

export function useFigures() {
  return useQuery({ queryKey: ["figures"], queryFn: api.listFigures });
}
