// The frame around a view of one text: top bar, sidebar, and the view itself.
import type { ReactNode } from "react";

import { useVersion } from "../api/queries";
import { pagePath, type ViewName } from "../lib/route";
import { Link } from "../router";
import { Sidebar } from "./Sidebar";

interface VersionShellProps {
  versionId: number;
  view: ViewName;
  title: string;
  children: ReactNode;
}

export function VersionShell({ versionId, view, title, children }: VersionShellProps) {
  const version = useVersion(versionId);
  return (
    <div className="shell view-shell">
      <header className="top-bar">
        <Link to="/" className="wordmark" title="Back to the library">
          PneuText
        </Link>
        {version.data && (
          <span className="work-title">
            {version.data.work.title}
            {version.data.work.author && <span className="quiet"> · {version.data.work.author}</span>}
          </span>
        )}
        {version.data?.first_page != null && (
          <Link className="nav-button back-to-text" to={pagePath(versionId, version.data.first_page)}>
            Back to the text
          </Link>
        )}
      </header>
      <div className="workspace view-workspace">
        <Sidebar version={version.data} currentView={view} />
        <main className="view" aria-labelledby="view-title">
          <h1 id="view-title">{title}</h1>
          {version.isError ? (
            <div role="alert" className="notice">
              <p>{version.error.message}</p>
            </div>
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}

/** What a view shows while loading, or instead of its content when the server fails. */
export function Loading({ error }: { error: Error | null }) {
  return error ? (
    <div role="alert" className="notice">
      <p>{error.message}</p>
    </div>
  ) : (
    <p className="quiet">Loading…</p>
  );
}
