import { type FormEvent, useEffect, useRef, useState } from "react";

import type { Division, Version } from "../api/client";
import { usePageShape, usePageText, useVersion } from "../api/queries";
import { type Mode, setPrefs, usePrefs } from "../lib/prefs";
import { pagePath } from "../lib/route";
import { Link, navigate } from "../router";
import { PageView } from "./PageView";

interface ReaderProps {
  versionId: number;
  page: number;
  line: number | null;
}

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

function Chapters({
  version,
  current,
}: {
  version: Version;
  current: Division | null;
}) {
  const chapters = version.divisions.filter((division) => division.page !== null);
  if (chapters.length === 0) return <p className="quiet">This text has no chapters.</p>;
  return (
    <ol className="chapter-list">
      {chapters.map((division) => (
        <li key={division.id}>
          <Link
            to={pagePath(version.id, division.page as number)}
            aria-current={current?.id === division.id ? "true" : undefined}
          >
            <span className="chapter-label">{division.label}</span>
            <span className="chapter-page">p. {division.page}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

function ModeSwitch({ mode }: { mode: Mode }) {
  return (
    <div className="mode-switch" role="group" aria-label="Reading mode">
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
  const { mode } = usePrefs();
  const version = useVersion(versionId);
  // Each mode asks only for its own projection: blank mode never requests the text.
  const pageText = usePageText(versionId, version.data?.edit_seq, page, mode === "text");
  const pageShape = usePageShape(versionId, version.data?.edit_seq, page, mode === "blank");
  const active = mode === "text" ? pageText : pageShape;
  const goToRef = useRef<HTMLInputElement>(null);
  const [goTo, setGoTo] = useState("");

  const shown = active.data;
  // Neighbours come from the version's page list, not from the page being loaded, so
  // turning pages quickly never waits on the network.
  const pages = version.data?.pages ?? [];
  const at = pages.indexOf(page);
  const prev = at > 0 ? (pages[at - 1] ?? null) : null;
  const next = at !== -1 ? (pages[at + 1] ?? null) : null;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "ArrowLeft" && prev !== null) navigate(pagePath(versionId, prev));
      else if (event.key === "ArrowRight" && next !== null) navigate(pagePath(versionId, next));
      else if (event.key === "g") {
        event.preventDefault();
        goToRef.current?.focus();
      } else if (event.key === "b") {
        setPrefs({ mode: mode === "text" ? "blank" : "text" });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [versionId, prev, next, mode]);

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
      <div className="workspace">
        <aside className="sidebar" aria-label="Chapters">
          <h2>Chapters</h2>
          {version.data && (
            <Chapters
              version={version.data}
              current={shown?.page === page ? shown.division : null}
            />
          )}
        </aside>
        <main className="stage">
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
              measure={version.data.measure}
              lines={pageText.data.lines}
              targetLine={pageText.data.page === page ? line : null}
            />
          ) : version.data && mode === "blank" && pageShape.data ? (
            <PageView
              mode="blank"
              page={pageShape.data.page}
              measure={version.data.measure}
              lines={pageShape.data.lines}
              targetLine={pageShape.data.page === page ? line : null}
            />
          ) : (
            <p className="quiet">Opening the page…</p>
          )}
        </main>
      </div>
    </div>
  );
}
