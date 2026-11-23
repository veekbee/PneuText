import { type FormEvent, useState } from "react";

import type { CorpusImportInput, CorpusImportPreview } from "../api/client";
import { useImportCorpus, usePreviewCorpusImport } from "../api/queries";
import { pagePath } from "../lib/route";
import { Link, navigate } from "../router";

const EMPTY: CorpusImportInput = {
  folder: "",
  work_code: "",
  title: "",
  author: "",
  label: "",
  language: "",
  file_pattern: null,
  allow_duplicate: false,
  source_format: "paged",
  first_page: 1,
  page_break: null,
  line_width: null,
};

const DEFAULT_PATTERN = "_corp_p(?P<page>\\d+)(?:_[A-Za-z0-9]+)?\\.txt$";
const DEFAULT_PAGE_BREAK = "\\{p\\d*\\}";
const DEFAULT_LINE_WIDTH = 65;

function Summary({ preview }: { preview: CorpusImportPreview }) {
  const { summary, problems } = preview;
  return (
    <section aria-labelledby="summary-title" className="import-summary">
      <h2 id="summary-title">What was found</h2>
      <dl className="counts">
        <div>
          <dt>Pages</dt>
          <dd>
            {summary.pages}
            {summary.first_page !== null && (
              <span className="quiet">
                {" "}
                ({summary.first_page}–{summary.last_page})
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt>Lines</dt>
          <dd>{summary.lines}</dd>
        </div>
        <div>
          <dt>Paragraphs</dt>
          <dd>{summary.paragraphs}</dd>
        </div>
        <div>
          <dt>Chapters</dt>
          <dd>{summary.chapters}</dd>
        </div>
        <div>
          <dt>Warnings</dt>
          <dd>{problems.length}</dd>
        </div>
      </dl>
      {problems.length > 0 && (
        <ul className="problems">
          {problems.map((problem, index) => (
            <li key={index}>{problem.message}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ImportCorpus() {
  const [input, setInput] = useState<CorpusImportInput>(EMPTY);
  const preview = usePreviewCorpusImport();
  const commit = useImportCorpus();
  const checked = preview.data;
  const tagged = input.source_format === "tagged";
  const error = commit.error ?? preview.error;

  function set<K extends keyof CorpusImportInput>(key: K, value: CorpusImportInput[K]): void {
    setInput((current) => ({ ...current, [key]: value }));
    preview.reset(); // the summary below describes the previous answers; drop it
    commit.reset();
  }

  function onCheck(event: FormEvent): void {
    event.preventDefault();
    commit.reset();
    preview.mutate(input);
  }

  function onImport(): void {
    commit.mutate(
      { ...input, allow_duplicate: checked?.existing_version_id != null },
      {
        onSuccess: (result) => {
          const first = result.summary.first_page;
          navigate(first === null ? "/" : pagePath(result.version_id, first));
        },
      },
    );
  }

  return (
    <div className="shell">
      <header className="top-bar">
        <Link to="/" className="wordmark" title="Back to the library">
          PneuText
        </Link>
      </header>
      <main className="stage">
        <section className="panel" aria-labelledby="import-title">
          <h1 id="import-title">Import a corpus</h1>
          <form onSubmit={onCheck} className="form">
            <fieldset className="choice">
              <legend>The text is</legend>
              <label>
                <input
                  type="radio"
                  name="source-format"
                  checked={!tagged}
                  onChange={() => set("source_format", "paged")}
                />
                A folder of page files
              </label>
              <label>
                <input
                  type="radio"
                  name="source-format"
                  checked={tagged}
                  onChange={() => set("source_format", "tagged")}
                />
                One tagged file
              </label>
            </fieldset>
            <p className="quiet">
              {tagged
                ? "One file holding the whole text, a paragraph per line, with a marker such as {p25} wherever a print page ends, and tags such as <chapter> and {section_break}. It records pages but not print lines, so lines are estimated. Nothing is changed in the file."
                : "A folder of text files, one per print page, with one print line per line and a blank line between paragraphs. Nothing is changed in that folder."}
            </p>
            <label>
              {tagged ? "Text file" : "Folder of page files"}
              <input
                required
                value={input.folder}
                placeholder={
                  tagged ? "/Users/you/Documents/book.txt" : "/Users/you/Documents/book-pages"
                }
                onChange={(event) => set("folder", event.target.value)}
              />
            </label>
            {tagged && (
              <>
                <label>
                  Number of the first page in the file
                  <input
                    type="number"
                    value={input.first_page}
                    onChange={(event) => set("first_page", Number(event.target.value))}
                  />
                  <small className="quiet">
                    Pages are counted from here, one for each page marker.
                  </small>
                </label>
                <label>
                  Characters per print line
                  <input
                    type="number"
                    min={20}
                    value={input.line_width ?? DEFAULT_LINE_WIDTH}
                    onChange={(event) => set("line_width", Number(event.target.value))}
                  />
                  <small className="quiet">
                    Used to estimate where lines break. Page numbers will match the print
                    edition; line numbers will not.
                  </small>
                </label>
              </>
            )}
            <label>
              Title
              <input
                required
                value={input.title}
                onChange={(event) => set("title", event.target.value)}
              />
            </label>
            <label>
              Author
              <input
                value={input.author ?? ""}
                onChange={(event) => set("author", event.target.value)}
              />
            </label>
            <label>
              Short code
              <input
                required
                value={input.work_code}
                placeholder="ab"
                pattern="[a-z][a-z0-9]*"
                title="Lower-case letters and digits, starting with a letter"
                onChange={(event) => set("work_code", event.target.value)}
              />
              <small className="quiet">Used when a note refers to a page, as in ab:45.</small>
            </label>
            <label>
              Edition
              <input
                value={input.label ?? ""}
                placeholder="First import"
                onChange={(event) => set("label", event.target.value)}
              />
            </label>
            {tagged ? (
              <details>
                <summary>Page marker</summary>
                <label>
                  Pattern that matches the end-of-page marker
                  <input
                    value={input.page_break ?? ""}
                    placeholder={DEFAULT_PAGE_BREAK}
                    spellCheck={false}
                    onChange={(event) => set("page_break", event.target.value || null)}
                  />
                </label>
              </details>
            ) : (
              <details>
                <summary>File names</summary>
                <label>
                  Pattern that finds the page number in a file name
                  <input
                    value={input.file_pattern ?? ""}
                    placeholder={DEFAULT_PATTERN}
                    spellCheck={false}
                    onChange={(event) => set("file_pattern", event.target.value || null)}
                  />
                </label>
              </details>
            )}
            <button type="submit" disabled={preview.isPending}>
              {preview.isPending ? "Checking…" : tagged ? "Check the file" : "Check the folder"}
            </button>
          </form>
          {error && (
            <div role="alert" className="notice">
              <p>{error.message}</p>
            </div>
          )}
          {checked && (
            <>
              <Summary preview={checked} />
              {checked.existing_version_id !== null && (
                <div role="alert" className="notice">
                  <p>These exact files have been imported before.</p>
                  {checked.summary.first_page !== null && (
                    <Link to={pagePath(checked.existing_version_id, checked.summary.first_page)}>
                      Open the existing version
                    </Link>
                  )}
                </div>
              )}
              <button type="button" onClick={onImport} disabled={commit.isPending}>
                {commit.isPending
                  ? "Importing…"
                  : checked.existing_version_id !== null
                    ? "Import a second copy"
                    : "Import"}
              </button>
            </>
          )}
        </section>
      </main>
    </div>
  );
}
