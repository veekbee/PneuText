// A link in progress: its first passage, kept while the reader turns pages to find the
// second. Held outside any component so it stays visible across navigation.
import { useSyncExternalStore } from "react";

import type { SpanInput } from "../api/client";

export interface LinkInProgress {
  versionId: number;
  span: SpanInput;
  /** How the first passage reads, such as "p. 8.3". */
  label: string;
}

let current: LinkInProgress | null = null;
const listeners = new Set<() => void>();

export function startLink(link: LinkInProgress): void {
  current = link;
  listeners.forEach((listener) => listener());
}

export function cancelLink(): void {
  if (current === null) return;
  current = null;
  listeners.forEach((listener) => listener());
}

export function useLinkInProgress(): LinkInProgress | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}
