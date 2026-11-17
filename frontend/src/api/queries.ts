import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type CorpusImportInput } from "./client";

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
