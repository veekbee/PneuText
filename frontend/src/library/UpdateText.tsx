import { type FormEvent, useState } from "react";

import type { CorpusUpdateInput, CorpusUpdateReport } from "../api/client";
import { usePreviewCorpusUpdate, useUpdateCorpus, useVersion } from "../api/queries";
import { pagePath } from "../lib/route";
import { Link } from "../router";

const DEFAULT_PATTERN = "_corp_p(?P<page>\\d+)(?:_[A-Za-z0-9]+)?\\.txt$";

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function PageLinks({ versionId, pages }: { versionId: number; pages: number[] }) {
  return (
    <span className="page-list">
      {pages.map((page, index) => (
        <span key={page}>
          {index > 0 && ", "}
          <Link to={pagePath(versionId, page)}>{page}</Link>
        </span>
      ))}
    </span>
  );
}

function Report({
  versionId,
  report,
  done,
}: {
  versionId: number;
  report: CorpusUpdateReport;
  done: boolean;
}) {
  if (report.up_to_date) {
    return (
      <section className="report" aria-label="What differs">
        <p>The files match the text as stored. There is nothing to update.</p>
      </section>
    );
  }
  const will = done ? "" : "will be ";
  return (
    <section className="report" aria-label="What differs">
      <ul>
        {report.changed_pages.length > 0 && (
          <li>
            {done ? "Changed" : "Changes on"}{" "}
            {report.changed_pages.length === 1 ? "page" : "pages"}{" "}
            <PageLinks versionId={versionId} pages={report.changed_pages} />, in{" "}
            {count(report.changed_paragraphs, "paragraph", "paragraphs")}
            {report.changed_paragraphs === 0 && " (only line or page breaks moved)"}.
          </li>
        )}
        {report.new_pages.length > 0 && (
          <li>
            {count(report.new_pages.length, "new page", "new pages")}:{" "}
            {report.new_pages[0]}
            {report.new_pages.length > 1 && ` to ${report.new_pages[report.new_pages.length - 1]}`}.
          </li>
        )}
        {report.moved_passages > 0 && (
          <li>
            {count(report.moved_passages, "marked passage", "marked passages")} {will}shifted
            along with {report.moved_passages === 1 ? "its" : "their"} words, reading the same
            as before.
          </li>
        )}
        {report.reworded_passages > 0 && (
          <li>
            {count(report.reworded_passages, "marked passage", "marked passages")}{" "}
            {done ? "now read" : "will read"} differently, because the correction falls inside{" "}
            {report.reworded_passages === 1 ? "it" : "them"}. Worth a look: page{" "}
            <PageLinks versionId={versionId} pages={report.reworded_pages} />.
          </li>
        )}
        {report.lost_passages > 0 && (
          <li>
            {count(report.lost_passages, "marked passage", "marked passages")}{" "}
            {done ? "lost" : "will lose"} {report.lost_passages === 1 ? "its" : "their"} words
            entirely, on page <PageLinks versionId={versionId} pages={report.lost_pages} />.{" "}
            {report.lost_passages === 1 ? "Its note is" : "Their notes are"} kept and listed
            in the to-do list to be placed again.
          </li>
        )}
      </ul>
      {report.problems.length > 0 && (
        <details>
          <summary>{count(report.problems.length, "remark", "remarks")} on the files</summary>
          <ul>
            {report.problems.map((problem, index) => (
              <li key={index}>{problem.message}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function UpdateText({ versionId }: { versionId: number }) {
  const version = useVersion(versionId);
  const [folder, setFolder] = useState("");
  const [filePattern, setFilePattern] = useState("");
  const preview = usePreviewCorpusUpdate(versionId);
  const commit = useUpdateCorpus(versionId);
  const error = commit.error ?? preview.error ?? version.error;
  const done = commit.data;
  const report = done ?? preview.data;
  const input: CorpusUpdateInput = { folder, file_pattern: filePattern || null };

  function forget(): void {
    preview.reset(); // the report below describes the previous answers; drop it
    commit.reset();
  }

  function onCheck(event: FormEvent): void {
    event.preventDefault();
    commit.reset();
    preview.mutate(input);
  }

  return (
    <div className="shell">
      <header className="top-bar">
        <Link to="/" className="wordmark" title="Back to the library">
          PneuText
        </Link>
        {version.data && <span className="work-title">{version.data.work.title}</span>}
      </header>
      <main className="stage">
        <section className="panel" aria-labelledby="update-title">
          <h1 id="update-title">Update the text</h1>
          <p className="quiet">
            For when you have corrected a page file, or added pages at the end. The folder is
            read again and compared with the text as stored; only what differs is changed,
            and notes, links and mentions stay with their words. Paragraphs must stay the
            same in number and order. The folder is checked first and nothing is written
            until you choose to update.
          </p>
          <form onSubmit={onCheck} className="form">
            <label>
              Folder of page files
              <input
                required
                value={folder}
                placeholder="/Users/you/Documents/book-pages"
                onChange={(event) => {
                  setFolder(event.target.value);
                  forget();
                }}
              />
            </label>
            <details>
              <summary>More options</summary>
              <label>
                Pattern that finds the page number in a file name
                <input
                  value={filePattern}
                  placeholder={DEFAULT_PATTERN}
                  spellCheck={false}
                  onChange={(event) => {
                    setFilePattern(event.target.value);
                    forget();
                  }}
                />
              </label>
            </details>
            <button type="submit" disabled={preview.isPending || commit.isPending}>
              {preview.isPending ? "Checking…" : "Check the folder"}
            </button>
          </form>
          {error && (
            <div role="alert" className="notice">
              <p>{error.message}</p>
            </div>
          )}
          {done && !done.up_to_date && (
            <div role="status" className="notice">
              <p>Updated.</p>
            </div>
          )}
          {report && <Report versionId={versionId} report={report} done={done !== undefined} />}
          {report && !done && !report.up_to_date && (
            <button type="button" disabled={commit.isPending} onClick={() => commit.mutate(input)}>
              {commit.isPending ? "Updating…" : "Update"}
            </button>
          )}
        </section>
      </main>
    </div>
  );
}
