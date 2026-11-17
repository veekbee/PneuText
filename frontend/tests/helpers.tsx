import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import type {
  Note,
  NoteType,
  PageShape,
  PageText,
  ShapeLine,
  TextLine,
  Version,
} from "../src/api/client";
import { resetPrefs } from "../src/lib/prefs";

type Handler = (body: unknown) => { status?: number; body: unknown };

/** Answer `fetch` from a table of "METHOD /path" handlers; anything else is a 404. */
export function mockApi(handlers: Record<string, Handler>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    const handler = handlers[key];
    if (handler === undefined) {
      return new Response(JSON.stringify({ detail: `No test handler for ${key}` }), {
        status: 404,
      });
    }
    const sent: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    const { status = 200, body } = handler(sent);
    // A 204 has no body, and the browser refuses to build one that does.
    return new Response(status === 204 ? null : JSON.stringify(body), { status });
  });
}

export function renderWithQuery(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

export function setUrl(url: string): void {
  window.history.replaceState(null, "", url);
}

/** Start a test with no remembered preferences. */
export function forgetPrefs(): void {
  window.localStorage.clear();
  resetPrefs();
}

let nextId = 1;

export function line(text: string, overrides: Partial<TextLine> = {}): TextLine {
  return {
    id: nextId++,
    segment_id: 1,
    kind: "paragraph",
    line_no: 1,
    start_offset: 0,
    length: [...text].length,
    starts_paragraph: false,
    ends_paragraph: false,
    text,
    highlights: [],
    mentions: [],
    ...overrides,
  };
}

export const VERSION: Version = {
  id: 1,
  work: { code: "fx", title: "The Fixture Book", author: "Nobody" },
  label: "First import",
  language: "",
  imported_at: "2026-01-01T00:00:00Z",
  edit_seq: 0,
  first_page: 7,
  last_page: 9,
  page_count: 3,
  measure: 20,
  pages: [7, 8, 9],
  divisions: [
    { id: 1, kind: "chapter", label: "I", page: 7, note_count: 5 },
    { id: 2, kind: "chapter", label: "II", page: 9, note_count: 0 },
  ],
};

export function pageOf(page: number, words: string): PageText {
  const first = VERSION.first_page as number;
  const last = VERSION.last_page as number;
  return {
    version_id: 1,
    edit_seq: 0,
    page,
    prev_page: page > first ? page - 1 : null,
    next_page: page < last ? page + 1 : null,
    division: VERSION.divisions[page >= 9 ? 1 : 0] ?? null,
    lines: [line(words, { line_no: 1, starts_paragraph: true, ends_paragraph: true })],
  };
}

export function shapeLine(length: number, overrides: Partial<ShapeLine> = {}): ShapeLine {
  return {
    id: nextId++,
    kind: "paragraph",
    page: 45,
    line_no: 1,
    starts_paragraph: false,
    ends_paragraph: false,
    length,
    highlights: [],
    mentions: [],
    ...overrides,
  };
}

export function shapeOf(page: number): PageShape {
  const { lines, ...rest } = pageOf(page, "x".repeat(page));
  return {
    ...rest,
    lines: lines.map((item) =>
      shapeLine(item.length, {
        id: item.id,
        page,
        line_no: item.line_no,
        starts_paragraph: item.starts_paragraph,
        ends_paragraph: item.ends_paragraph,
      }),
    ),
  };
}

export const TYPES: NoteType[] = [
  { id: 1, name: "Clarification", code: "cl", color: "#7d9bbd", sort: 10, role: "note" },
  { id: 2, name: "Comment", code: "c", color: "#d9b44a", sort: 20, role: "note" },
  { id: 8, name: "Chapter summary", code: "cs", color: "#b0b0b0", sort: 90, role: "chapter_summary" },
];

export function noteOf(id: number, overrides: Partial<Note> = {}): Note {
  return {
    id,
    version_id: 1,
    type_id: 2,
    scope: "span",
    level: 1,
    status: "draft",
    body_md: "",
    body: { type: "document", children: [] },
    tags: [],
    legacy_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    anchor: { start_segment_id: 1, start_offset: 0, end_segment_id: 1, end_offset: 5, status: "ok" },
    start: { page: 7, line_no: 1 },
    end: { page: 7, line_no: 1 },
    backlinks: [],
    ...overrides,
  };
}

/** A parsed body holding one plain paragraph. */
export function bodyOf(text: string): Note["body"] {
  return {
    type: "document",
    children: [{ type: "paragraph", children: [{ type: "text", text }] }],
  };
}

/** Select text on the page as a reader would, then release the mouse. */
export function selectText(
  startNode: Node,
  startOffset: number,
  endNode: Node,
  endOffset: number,
): void {
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
  document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
}

export interface Sent {
  method: string;
  path: string;
  query: Record<string, string>;
  body: unknown;
}

/**
 * Answer `fetch` by method and path, ignoring the query string (which is passed to the
 * handler). Records every request that changes something.
 */
export function mockServer(
  handlers: Record<string, (request: Sent) => { status?: number; body: unknown }>,
) {
  const sent: Sent[] = [];
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = new URL(String(input), "http://local");
    const method = init?.method ?? "GET";
    let body: unknown = undefined;
    if (typeof init?.body === "string") body = JSON.parse(init.body);
    else if (init?.body instanceof Blob) body = init.body;
    const request: Sent = {
      method,
      path: url.pathname,
      query: Object.fromEntries(url.searchParams),
      body,
    };
    if (method !== "GET") sent.push(request);
    const handler = handlers[`${method} ${url.pathname}`];
    if (handler === undefined) {
      return new Response(JSON.stringify({ detail: `No test handler for ${method} ${url.pathname}` }), {
        status: 404,
      });
    }
    const { status = 200, body: answer } = handler(request);
    return new Response(status === 204 ? null : JSON.stringify(answer), { status });
  });
  return { sent, fetchMock };
}
