// One search box: a page reference goes to the place; free text is looked for in the
// corpus and in notes, shown separately. The corpus is not searched in blank mode.
import { type FormEvent, type RefObject, useEffect, useState } from "react";

import type { NoteType, SearchResults } from "../api/client";
import { useSearch } from "../api/queries";
import { isVisible, type NoteFilter } from "../lib/filters";
import { pagePath } from "../lib/route";
import { navigate } from "../router";

interface SearchBoxProps {
  versionId: number;
  /** In blank mode the corpus is never searched and never shown. */
  searchCorpus: boolean;
  types: NoteType[];
  filter: NoteFilter;
  inputRef: RefObject<HTMLInputElement | null>;
  onOpenNote: (noteId: number) => void;
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return settled;
}

function Results({
  results,
  props,
  onChoose,
}: {
  results: SearchResults;
  props: Pick<SearchBoxProps, "versionId" | "types" | "filter">;
  onChoose: (href: string, note?: number) => void;
}) {
  const typeName = new Map(props.types.map((type) => [type.id, type.name]));
  const notes = results.notes.filter((hit) => isVisible(hit, props.filter));
  const reference = results.reference;
  const nothing = reference === null && notes.length === 0 && !results.corpus?.length;
  return (
    <div className="search-results" role="region" aria-label="Search results">
      {reference !== null && (
        <section aria-label="Go to">
          <h3>Go to</h3>
          <button
            type="button"
            onClick={() => onChoose(pagePath(props.versionId, reference.page, reference.line_no))}
          >
            Page {reference.page}
            {reference.line_no !== null && `, line ${reference.line_no}`}
          </button>
        </section>
      )}
      {results.corpus !== null && results.corpus.length > 0 && (
        <section aria-label="In the text">
          <h3>In the text</h3>
          <ul>
            {results.corpus.map((hit, index) => (
              <li key={index}>
                <button
                  type="button"
                  onClick={() => onChoose(pagePath(props.versionId, hit.page, hit.line_no))}
                >
                  <span className="hit-place">
                    {hit.page}
                    {hit.line_no !== null && `.${hit.line_no}`}
                  </span>
                  <span className="hit-line">
                    {hit.before}
                    <mark>{hit.match}</mark>
                    {hit.after}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {notes.length > 0 && (
        <section aria-label="In notes">
          <h3>In notes</h3>
          <ul>
            {notes.map((hit) => {
              const page = hit.page;
              return (
                <li key={hit.note_id}>
                  <button
                    type="button"
                    disabled={page === null}
                    onClick={() =>
                      page !== null &&
                      onChoose(pagePath(props.versionId, page, hit.line_no), hit.note_id)
                    }
                  >
                    <span className="hit-place">
                      {typeName.get(hit.type_id) ?? "Note"}
                      {page !== null && `, p. ${page}`}
                    </span>
                    <span className="hit-line">{hit.excerpt}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {nothing && <p className="quiet">Nothing found.</p>}
      {results.corpus === null && (
        <p className="quiet">The text itself is not searched in blank mode.</p>
      )}
    </div>
  );
}

export function SearchBox({
  versionId,
  searchCorpus,
  types,
  filter,
  inputRef,
  onOpenNote,
}: SearchBoxProps) {
  const [typed, setTyped] = useState("");
  const [open, setOpen] = useState(false);
  const query = useDebounced(typed.trim(), 200);
  const search = useSearch(versionId, query, searchCorpus);
  // Results shown belong to what is typed now, not to an earlier query still on screen.
  const results = query !== "" && search.data?.query === query ? search.data : null;

  function choose(href: string, note?: number): void {
    setOpen(false);
    inputRef.current?.blur();
    navigate(href);
    if (note !== undefined) onOpenNote(note);
  }

  function onSubmit(event: FormEvent): void {
    event.preventDefault();
    // Enter follows a page reference straight away.
    const reference = results?.reference;
    if (reference) choose(pagePath(versionId, reference.page, reference.line_no));
  }

  return (
    <form className="search" role="search" onSubmit={onSubmit}>
      <input
        ref={inputRef}
        type="search"
        aria-label="Search"
        placeholder="Search, or go to 45.12"
        value={typed}
        onChange={(event) => {
          setTyped(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
            event.currentTarget.blur();
          }
        }}
      />
      {open && results !== null && (
        <Results results={results} props={{ versionId, types, filter }} onChoose={choose} />
      )}
      {open && search.isError && (
        <div className="search-results" role="alert">
          <p>{search.error.message}</p>
        </div>
      )}
    </form>
  );
}
