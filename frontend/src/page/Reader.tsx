import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type MentionInput,
  type NoteUpdateInput,
  type ShapeLine,
  type TextLine,
} from "../api/client";
import {
  useCategories,
  useChange,
  useCreateNote,
  useCreatePassageLink,
  useDeleteNote,
  useDeletePassageLink,
  useFigures,
  useNoteTypes,
  usePageLinks,
  usePageNotes,
  usePageShape,
  usePageText,
  useUpdateNote,
  useVersion,
} from "../api/queries";
import { TagEntityForm } from "../entities/TagEntityForm";
import { isVisible, type NoteFilter } from "../lib/filters";
import { cancelLink, startLink, useLinkInProgress } from "../lib/linkTray";
import { type Mode, setPrefs, usePrefs } from "../lib/prefs";
import { pagePath } from "../lib/route";
import {
  citationFor,
  readSelection,
  referenceFor,
  type RowPoint,
  spanFromRows,
  type SpanSelection,
} from "../lib/selection";
import { APP_ENV } from "../notes/env";
import { NoteFilters } from "../notes/NoteFilters";
import { NotesPanel } from "../notes/NotesPanel";
import { Link, navigate } from "../router";
import { SearchBox } from "../search/SearchBox";
import { Sidebar } from "../shell/Sidebar";
import { PageView } from "./PageView";
import { SelectionPopover } from "./SelectionPopover";

interface ReaderProps {
  versionId: number;
  page: number;
  line: number | null;
}

interface Selected {
  selection: SpanSelection;
  /** The page the selection was made on; it does not outlive that page. */
  page: number;
  /** The page the passage begins on (an earlier page when it was carried over). */
  startPage: number;
  from: RowPoint;
  rect: { left: number; top: number; bottom: number; width: number };
}

/** A new note starts as an empty first-reading draft. */
const NEW_NOTE = { level: 1, status: "draft" as const, body_md: "", tags: [] as string[] };

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

function ModeSwitch({ mode }: { mode: Mode }) {
  return (
    <div className="segmented mode-switch" role="group" aria-label="Reading mode">
      {(["text", "blank"] as const).map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={mode === option}
          title={option === "text" ? "Show the words (b)" : "Show the page's shape only (b)"}
          onClick={() => setPrefs({ mode: option })}
        >
          {option === "text" ? "Text" : "Blank"}
        </button>
      ))}
    </div>
  );
}

export function Reader({ versionId, page, line }: ReaderProps) {
  const { mode, level, hiddenTypes, showMentions } = usePrefs();
  const queryClient = useQueryClient();
  const version = useVersion(versionId);
  const editSeq = version.data?.edit_seq;
  // Each mode asks only for its own projection: blank mode never requests the text.
  const pageText = usePageText(versionId, editSeq, page, mode === "text");
  const pageShape = usePageShape(versionId, editSeq, page, mode === "blank");
  const active = mode === "text" ? pageText : pageShape;
  const noteTypes = useNoteTypes();
  const pageNotes = usePageNotes(versionId, page);
  const pageLinks = usePageLinks(versionId, page);
  const figures = useFigures();
  const createNote = useCreateNote(versionId);
  const updateNote = useUpdateNote(versionId);
  const deleteNote = useDeleteNote(versionId);
  const categories = useCategories();
  const createMention = useChange((input: MentionInput) => api.createMention(versionId, input));
  const createLink = useCreatePassageLink(versionId);
  const deleteLink = useDeletePassageLink(versionId);
  // A link in progress is held outside this page, so it survives turning pages.
  const inProgress = useLinkInProgress();
  const linking = inProgress !== null && inProgress.versionId === versionId ? inProgress : null;

  const stage = useRef<HTMLElement>(null);
  const goToRef = useRef<HTMLInputElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [goTo, setGoTo] = useState("");
  const [statusFilter, setStatusFilter] = useState<"draft" | "ready" | null>(null);
  const [selection, setSelected] = useState<Selected | null>(null);
  // A selection belongs to the page and mode it was made in.
  const selected = selection !== null && selection.page === page && mode === "text" ? selection : null;
  /** A passage begun on an earlier page, waiting for its end to be selected. */
  const [carried, setCarried] = useState<{ page: number; from: RowPoint } | null>(null);
  /** A note whose passage is being chosen again. */
  const [reselecting, setReselecting] = useState<number | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number[]>([]);
  const [scrollTo, setScrollTo] = useState<{ note: number; tick: number } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [lastType, setLastType] = useState<number | null>(null);
  /** Whether the selection is being tagged as an entity, and the category used last. */
  const [tagging, setTagging] = useState(false);
  const [lastCategory, setLastCategory] = useState<number | null>(null);

  const shown = active.data;
  // Neighbours come from the version's page list, not from the page being loaded, so
  // turning pages quickly never waits on the network.
  const pages = useMemo(() => version.data?.pages ?? [], [version.data]);
  const at = pages.indexOf(page);
  const prev = at > 0 ? (pages[at - 1] ?? null) : null;
  const next = at !== -1 ? (pages[at + 1] ?? null) : null;

  const types = useMemo(() => noteTypes.data ?? [], [noteTypes.data]);
  const typeColors = useMemo(
    () => Object.fromEntries(types.map((type) => [type.id, type.color])),
    [types],
  );
  const categoryColors = useMemo(
    () => Object.fromEntries((categories.data ?? []).map((item) => [item.id, item.color])),
    [categories.data],
  );
  const defaultType = lastType ?? types[0]?.id ?? null;

  // ---- What the reader's filters leave visible --------------------------------
  const filter: NoteFilter = useMemo(
    () => ({ level, hiddenTypes, status: statusFilter }),
    [level, hiddenTypes, statusFilter],
  );
  const allNotes = useMemo(() => pageNotes.data ?? [], [pageNotes.data]);
  const visibleNotes = useMemo(
    () => allNotes.filter((note) => isVisible(note, filter)),
    [allNotes, filter],
  );
  const statusOf = useMemo(
    () => new Map(allNotes.map((note) => [note.id, note.status])),
    [allNotes],
  );
  // First reading hides a level 2 note and with it any backlink that comes from it.
  const showBacklink = useCallback(
    (backlink: { type_id: number; level: number; status: string }) => isVisible(backlink, filter),
    [filter],
  );
  const filterLines = useCallback(
    <T extends TextLine | ShapeLine>(lines: T[]): T[] =>
      lines.map((item) => ({
        ...item,
        highlights: item.highlights.filter((mark) =>
          isVisible({ ...mark, status: statusOf.get(mark.annotation_id) }, filter),
        ),
        // The underline on entity mentions can be switched off.
        mentions: showMentions ? item.mentions : [],
      })),
    [filter, statusOf, showMentions],
  );
  const textLines = useMemo(
    () => (pageText.data ? filterLines(pageText.data.lines) : []),
    [pageText.data, filterLines],
  );
  const shapeLines = useMemo(
    () => (pageShape.data ? filterLines(pageShape.data.lines) : []),
    [pageShape.data, filterLines],
  );

  // ---- Selecting a passage -----------------------------------------------------
  const clearSelection = useCallback(() => {
    window.getSelection()?.removeAllRanges();
    setSelected(null);
    setTagging(false);
  }, []);

  /** The lines of every page from one to another, for a passage that crosses pages. */
  const linesBetween = useCallback(
    async (firstPage: number, lastPage: number): Promise<TextLine[]> => {
      const span = pages.filter((number) => number >= firstPage && number <= lastPage);
      const loaded = await Promise.all(
        span.map((number) =>
          queryClient.fetchQuery({
            queryKey: ["page-text", versionId, editSeq, number],
            queryFn: () => api.getPageText(versionId, number),
            staleTime: Infinity,
          }),
        ),
      );
      return loaded.flatMap((item) => item.lines);
    },
    [pages, queryClient, versionId, editSeq],
  );

  const saveReselection = useCallback(
    (noteId: number, selection: SpanSelection) => {
      updateNote.mutate(
        { noteId, changes: { span: selection.span } },
        { onError: (error) => setMessage(error.message) },
      );
      setReselecting(null);
      clearSelection();
    },
    [updateNote, clearSelection],
  );

  const readPageSelection = useCallback(async () => {
    if (mode !== "text" || pageText.data?.page !== page) return;
    const body = stage.current?.querySelector<HTMLElement>(".page-body");
    const read = body ? readSelection(body) : null;
    if (read === null) {
      setSelected(null);
      return;
    }
    const pageLines = pageText.data.lines;
    let selection: SpanSelection | null;
    let startPage = page;
    let from = read.from;
    if (carried !== null && carried.page < page) {
      // The passage began on an earlier page: it runs from there to the end of this
      // selection, across every page between.
      const before = await linesBetween(carried.page, page - 1);
      selection = spanFromRows([...before, ...pageLines], carried.from, {
        row: before.length + read.to.row,
        utf16: read.to.utf16,
      });
      startPage = carried.page;
      from = carried.from;
    } else {
      selection = spanFromRows(pageLines, read.from, read.to);
    }
    if (selection === null) {
      setSelected(null);
      return;
    }
    if (reselecting !== null) {
      saveReselection(reselecting, selection);
      setCarried(null);
      return;
    }
    const { left, top, bottom, width } = read.rect;
    setSelected({ selection, page, startPage, from, rect: { left, top, bottom, width } });
  }, [mode, page, pageText.data, carried, reselecting, linesBetween, saveReselection]);

  useEffect(() => {
    const onRelease = (event: Event): void => {
      // Releases inside the popover act on the selection; they do not change it.
      if (event.target instanceof Element && event.target.closest(".popover")) return;
      void readPageSelection();
    };
    document.addEventListener("mouseup", onRelease);
    document.addEventListener("keyup", onRelease);
    return () => {
      document.removeEventListener("mouseup", onRelease);
      document.removeEventListener("keyup", onRelease);
    };
  }, [readPageSelection]);

  // ---- Creating, editing and deleting notes ------------------------------------
  const addNote = useCallback(
    (typeId: number, openEditor: boolean) => {
      if (selected === null || editSeq === undefined) return;
      const { selection, startPage } = selected;
      setMessage(null);
      createNote.mutate(
        {
          input: { ...NEW_NOTE, type_id: typeId, scope: "span", span: selection.span },
          page,
          editSeq,
          tempId: -Date.now(),
          marks: selection.marks,
          start: { page: startPage, line_no: selection.first.line_no },
          end: { page, line_no: selection.last.line_no },
        },
        {
          onSuccess: (note) => {
            if (openEditor) setEditing(note.id);
            setScrollTo({ note: note.id, tick: Date.now() });
          },
          onError: (error) => setMessage(error.message),
        },
      );
      setLastType(typeId);
      setCarried(null);
      clearSelection();
    },
    [selected, editSeq, createNote, page, clearSelection],
  );

  const addUnitNote = useCallback(
    (scope: "page" | "chapter", divisionId?: number) => {
      const typeId =
        scope === "chapter"
          ? (types.find((type) => type.role === "chapter_summary")?.id ?? defaultType)
          : defaultType;
      if (typeId === null || editSeq === undefined) return;
      setMessage(null);
      createNote.mutate(
        {
          input:
            scope === "page"
              ? { ...NEW_NOTE, type_id: typeId, scope, page }
              : { ...NEW_NOTE, type_id: typeId, scope, division_id: divisionId },
          page,
          editSeq,
          tempId: -Date.now(),
          marks: [],
          start: { page, line_no: null },
          end: { page, line_no: null },
        },
        {
          onSuccess: (note) => {
            setEditing(note.id);
            setScrollTo({ note: note.id, tick: Date.now() });
          },
          onError: (error) => setMessage(error.message),
        },
      );
    },
    [types, defaultType, editSeq, createNote, page],
  );

  function saveNote(noteId: number, changes: NoteUpdateInput): void {
    updateNote.mutate({ noteId, changes }, { onSuccess: () => setEditing(null) });
  }

  function removeNote(noteId: number): void {
    deleteNote.mutate(noteId, {
      onSuccess: () => setEditing(null),
      onError: (error) => setMessage(error.message),
    });
  }

  /** Tag the selection: assign it to an entity, or record it as a time. */
  function tagSelection(input: Omit<MentionInput, "span">): void {
    if (selected === null) return;
    createMention.mutate(
      { ...input, span: selected.selection.span },
      {
        onSuccess: () => {
          setLastCategory(input.category_id);
          clearSelection();
        },
      },
    );
  }

  /** Start a passage-to-passage link from the selection, or complete the one in progress. */
  const linkSelection = useCallback(() => {
    if (selected === null) return;
    const { selection, startPage } = selected;
    if (linking === null) {
      startLink({
        versionId,
        span: selection.span,
        label: citationFor(
          { page: startPage, line_no: selection.first.line_no },
          { page, line_no: selection.last.line_no },
        ),
      });
    } else {
      setMessage(null);
      createLink.mutate(
        { source: linking.span, target: selection.span },
        { onSuccess: cancelLink, onError: (error) => setMessage(error.message) },
      );
    }
    setCarried(null);
    clearSelection();
  }, [selected, linking, versionId, page, createLink, clearSelection]);

  function continueOnNextPage(): void {
    if (selected === null || next === null) return;
    setCarried({ page: selected.startPage, from: selected.from });
    clearSelection();
    navigate(pagePath(versionId, next));
  }

  // ---- Keyboard ----------------------------------------------------------------
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        // Esc dismisses the popover first; with nothing selected it cancels a link.
        if (selected !== null) clearSelection();
        else cancelLink();
        setCarried(null);
        setReselecting(null);
        return;
      }
      if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "ArrowLeft" && prev !== null) navigate(pagePath(versionId, prev));
      else if (event.key === "ArrowRight" && next !== null) navigate(pagePath(versionId, next));
      else if (event.key === "g") {
        event.preventDefault();
        goToRef.current?.focus();
      } else if (event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
      } else if (event.key === "l" && selected) {
        event.preventDefault();
        linkSelection();
      } else if (event.key === "e" && selected) {
        event.preventDefault();
        createMention.reset();
        setTagging(true);
      } else if (event.key === "b") {
        setPrefs({ mode: mode === "text" ? "blank" : "text" });
      } else if ((event.key === "n" || event.key === "h") && selected && defaultType !== null) {
        event.preventDefault();
        addNote(defaultType, event.key === "n");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    versionId,
    prev,
    next,
    mode,
    selected,
    defaultType,
    addNote,
    clearSelection,
    linkSelection,
    createMention,
  ]);

  useEffect(() => {
    if (line === null || shown?.page !== page) return;
    document.getElementById(`l${line}`)?.scrollIntoView?.({ block: "center" });
  }, [line, page, shown?.page]);

  function onGoTo(event: FormEvent): void {
    event.preventDefault();
    const target = Number.parseInt(goTo, 10);
    if (Number.isFinite(target)) {
      navigate(pagePath(versionId, target));
      setGoTo("");
      goToRef.current?.blur();
    }
  }

  if (version.isError) {
    return (
      <div className="shell">
        <header className="top-bar">
          <Link to="/" className="wordmark">
            PneuText
          </Link>
        </header>
        <main className="stage">
          <div role="alert" className="notice">
            <p>{version.error.message}</p>
            <Link to="/">Back to the library</Link>
          </div>
        </main>
      </div>
    );
  }

  const division = shown?.page === page ? shown.division : null;
  const pageView = {
    measure: version.data?.measure ?? 0,
    typeColors,
    categoryColors,
    activeNotes: hovered,
    onHoverNotes: setHovered,
    onClickNotes: (notes: number[]) => {
      const note = notes[notes.length - 1];
      if (note !== undefined) setScrollTo({ note, tick: Date.now() });
    },
  };

  return (
    <div className="shell">
      <header className="top-bar">
        <Link to="/" className="wordmark" title="Back to the library">
          PneuText
        </Link>
        {version.data && (
          <span className="work-title">
            {version.data.work.title}
            {version.data.work.author && (
              <span className="quiet"> · {version.data.work.author}</span>
            )}
          </span>
        )}
        <SearchBox
          versionId={versionId}
          searchCorpus={mode === "text"}
          types={types}
          filter={filter}
          inputRef={searchRef}
          onOpenNote={(note) => setScrollTo({ note, tick: Date.now() })}
        />
        <ModeSwitch mode={mode} />
        <nav className="page-nav" aria-label="Pages">
          {prev === null ? (
            <span className="nav-button is-disabled" aria-disabled="true">
              ‹ Previous
            </span>
          ) : (
            <Link className="nav-button" to={pagePath(versionId, prev)}>
              ‹ Previous
            </Link>
          )}
          <form onSubmit={onGoTo} className="go-to">
            <label htmlFor="go-to-page">Go to page</label>
            <input
              id="go-to-page"
              ref={goToRef}
              inputMode="numeric"
              pattern="[0-9]*"
              value={goTo}
              placeholder={String(page)}
              onChange={(event) => setGoTo(event.target.value)}
            />
          </form>
          {next === null ? (
            <span className="nav-button is-disabled" aria-disabled="true">
              Next ›
            </span>
          ) : (
            <Link className="nav-button" to={pagePath(versionId, next)}>
              Next ›
            </Link>
          )}
        </nav>
      </header>
      <div className="filter-bar">
        <NoteFilters
          level={level}
          hiddenTypes={hiddenTypes}
          types={types}
          onLevel={(value) => setPrefs({ level: value })}
          onHiddenTypes={(value) => setPrefs({ hiddenTypes: value })}
        />
        <label className="mention-toggle">
          <input
            type="checkbox"
            checked={showMentions}
            onChange={(event) => setPrefs({ showMentions: event.target.checked })}
          />
          Underline entities
        </label>
        {linking !== null && (
          <div className="link-tray" role="status" aria-label="Link in progress">
            <span>
              Linking from <strong>{linking.label}</strong>. Select the passage to link it to,
              then choose Link here.
            </span>
            <button type="button" className="quiet-button" onClick={cancelLink}>
              Cancel
            </button>
          </div>
        )}
      </div>
      <div className="workspace">
        <Sidebar version={version.data} currentDivision={division} />
        <main className="stage" ref={stage}>
          {message !== null && (
            <div role="alert" className="notice">
              <p>{message}</p>
              <button type="button" className="quiet-button" onClick={() => setMessage(null)}>
                Dismiss
              </button>
            </div>
          )}
          {carried !== null && (
            <div role="status" className="notice">
              <p>
                A passage begun on page {carried.page} is being continued. Select the words it
                ends with on this page, or press Esc to cancel.
              </p>
            </div>
          )}
          {reselecting !== null && (
            <div role="status" className="notice">
              <p>Select the passage this note should attach to, or press Esc to cancel.</p>
            </div>
          )}
          {active.isError ? (
            <div role="alert" className="notice">
              <p>{active.error.message}</p>
              {version.data?.first_page != null && (
                <Link to={pagePath(versionId, version.data.first_page)}>
                  Go to the first page
                </Link>
              )}
            </div>
          ) : version.data && mode === "text" && pageText.data ? (
            <PageView
              mode="text"
              page={pageText.data.page}
              lines={textLines}
              targetLine={pageText.data.page === page ? line : null}
              {...pageView}
            />
          ) : version.data && mode === "blank" && pageShape.data ? (
            <PageView
              mode="blank"
              page={pageShape.data.page}
              lines={shapeLines}
              targetLine={pageShape.data.page === page ? line : null}
              {...pageView}
            />
          ) : (
            <p className="quiet">Opening the page…</p>
          )}
        </main>
        <NotesPanel
          notes={visibleNotes}
          hiddenCount={allNotes.length - visibleNotes.length}
          types={types}
          versionId={versionId}
          workCode={version.data?.work.code ?? ""}
          figures={figures.data ?? []}
          env={APP_ENV}
          page={page}
          backlinks={(pageLinks.data?.backlinks ?? []).filter(showBacklink)}
          passageLinks={pageLinks.data?.passages ?? []}
          showBacklink={showBacklink}
          onDeleteLink={(linkId) =>
            deleteLink.mutate(linkId, { onError: (error) => setMessage(error.message) })
          }
          readOnly={mode === "blank"}
          activeNotes={hovered}
          editingNote={editing}
          scrollTo={scrollTo}
          saving={updateNote.isPending}
          error={updateNote.error?.message ?? null}
          statusFilter={statusFilter}
          onStatusFilter={setStatusFilter}
          onHover={setHovered}
          onEdit={(note) => {
            updateNote.reset();
            setEditing(note);
          }}
          onSave={saveNote}
          onDelete={removeNote}
          onReselect={(note) => {
            setEditing(null);
            setReselecting(note);
          }}
          onNewPageNote={() => addUnitNote("page")}
          onNewChapterNote={division ? () => addUnitNote("chapter", division.id) : null}
        />
      </div>
      {selected !== null && version.data && (
        <SelectionPopover
          rect={selected.rect}
          types={types.filter((type) => type.role === "note" || type.role === "definition")}
          defaultType={defaultType}
          reference={referenceFor(
            version.data.work.code,
            { page: selected.startPage, line_no: selected.selection.first.line_no },
            { page, line_no: selected.selection.last.line_no },
          )}
          canContinue={next !== null}
          linking={linking !== null}
          onLink={linkSelection}
          onTagEntity={() => {
            createMention.reset();
            setTagging(true);
          }}
          tagForm={
            tagging ? (
              <TagEntityForm
                versionId={versionId}
                words={selected.selection.span.exact.replace(/\s+/g, " ").trim()}
                categories={categories.data ?? []}
                defaultCategory={lastCategory}
                saving={createMention.isPending}
                error={createMention.error?.message ?? null}
                onTag={tagSelection}
                onCancel={() => setTagging(false)}
              />
            ) : null
          }
          onNote={(typeId) => addNote(typeId, true)}
          onHighlight={(typeId) => addNote(typeId, false)}
          onCopied={clearSelection}
          onContinue={continueOnNextPage}
        />
      )}
    </div>
  );
}
