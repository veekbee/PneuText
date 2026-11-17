import { type FormEvent, useState } from "react";

import type { LegacyImportInput } from "../api/client";
import { useImportCommentary, usePreviewCommentaryImport, useVersion } from "../api/queries";
import { pagePath } from "../lib/route";
import { Link } from "../router";
import { LegacyReportView } from "./LegacyReportView";

const DEFAULT_PATTERN = "_comm_p(?P<page>\\d+)\\.txt$";

interface Answers {
  folder: string;
  filePattern: string;
  pageRefCommands: string;
  figuresFolder: string;
}

const EMPTY: Answers = { folder: "", filePattern: "", pageRefCommands: "", figuresFolder: "" };

function toInput(answers: Answers): LegacyImportInput {
  return {
    folder: answers.folder,
    file_pattern: answers.filePattern || null,
    page_ref_commands: answers.pageRefCommands
      .split(",")
      .map((name) => name.trim())
      .filter(Boolean),
    figures_folder: answers.figuresFolder || null,
  };
}

export function ImportCommentary({ versionId }: { versionId: number }) {
  const version = useVersion(versionId);
  const [answers, setAnswers] = useState<Answers>(EMPTY);
  const preview = usePreviewCommentaryImport(versionId);
  const commit = useImportCommentary(versionId);
  const error = commit.error ?? preview.error ?? version.error;
  const done = commit.data;
  const report = done ?? preview.data;

  function set<K extends keyof Answers>(key: K, value: string): void {
    setAnswers((current) => ({ ...current, [key]: value }));
    preview.reset(); // the report below describes the previous answers; drop it
    commit.reset();
  }

  function onCheck(event: FormEvent): void {
    event.preventDefault();
    commit.reset();
    preview.mutate(toInput(answers));
  }

  const firstPage = report?.pages[0] ?? version.data?.first_page ?? null;
  return (
    <div className="shell">
      <header className="top-bar">
        <Link to="/" className="wordmark" title="Back to the library">
          PneuText
        </Link>
        {version.data && <span className="work-title">{version.data.work.title}</span>}
      </header>
      <main className="stage">
        <section className="panel" aria-labelledby="import-title">
          <h1 id="import-title">Import old commentary</h1>
          <p className="quiet">
            Reads the hand-made commentary files for this text: each page&rsquo;s text with
            inline markup, then the notes. The folder is checked first and nothing is
            written until you choose to import. Nothing is changed in that folder.
          </p>
          <form onSubmit={onCheck} className="form">
            <label>
              Folder of commentary files
              <input
                required
                value={answers.folder}
                placeholder="/Users/you/Documents/book-commentary"
                onChange={(event) => set("folder", event.target.value)}
              />
            </label>
            <details>
              <summary>More options</summary>
              <label>
                Pattern that finds the page number in a file name
                <input
                  value={answers.filePattern}
                  placeholder={DEFAULT_PATTERN}
                  spellCheck={false}
                  onChange={(event) => set("filePattern", event.target.value)}
                />
              </label>
              <label>
                LaTeX commands that cite a page of this text
                <input
                  value={answers.pageRefCommands}
                  placeholder="for example: pageref, pr"
                  spellCheck={false}
                  onChange={(event) => set("pageRefCommands", event.target.value)}
                />
                <small className="quiet">
                  Separated by commas, without the backslash. Each becomes a page reference.
                </small>
              </label>
              <label>
                Folder of figure files
                <input
                  value={answers.figuresFolder}
                  placeholder="The commentary folder, or its figures folder"
                  onChange={(event) => set("figuresFolder", event.target.value)}
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
          {done && (
            <div role="status" className="notice">
              <p>
                Imported. Every note is a draft; flagged notes and time tags without a value
                are waiting in the to-do list.
              </p>
              {firstPage !== null && (
                <Link to={pagePath(versionId, firstPage)}>Open page {firstPage}</Link>
              )}
            </div>
          )}
          {report && <LegacyReportView report={report} />}
          {report && !done && (
            <button
              type="button"
              disabled={commit.isPending || report.pages.length === 0}
              onClick={() => commit.mutate(toInput(answers))}
            >
              {commit.isPending ? "Importing…" : "Import"}
            </button>
          )}
        </section>
      </main>
    </div>
  );
}
