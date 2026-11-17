import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import type { PageShape, PageText, ShapeLine, TextLine, Version } from "../src/api/client";
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
    return new Response(JSON.stringify(body), { status });
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
    { id: 1, kind: "chapter", label: "I", page: 7 },
    { id: 2, kind: "chapter", label: "II", page: 9 },
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
