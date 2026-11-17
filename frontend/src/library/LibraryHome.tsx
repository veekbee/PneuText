import type { VersionSummary } from "../api/client";
import { useLibrary, useVersions } from "../api/queries";
import { commentaryImportPath, pagePath } from "../lib/route";
import { Link } from "../router";

function pageRange(version: VersionSummary): string {
  if (version.first_page === null || version.last_page === null) return "no pages";
  const count = `${version.page_count} ${version.page_count === 1 ? "page" : "pages"}`;
  return `${count}, ${version.first_page}–${version.last_page}`;
}

export function VersionList({ versions }: { versions: VersionSummary[] }) {
  return (
    <ul className="version-list">
      {versions.map((version) => (
        <li key={version.id}>
          {version.first_page === null ? (
            <span className="version-title">{version.work.title}</span>
          ) : (
            <Link className="version-title" to={pagePath(version.id, version.first_page)}>
              {version.work.title}
            </Link>
          )}
          <span className="quiet">
            {version.work.author && `${version.work.author} · `}
            {version.label} · {pageRange(version)}
          </span>
          <Link className="version-action" to={commentaryImportPath(version.id)}>
            Import old commentary
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function LibraryHome() {
  const library = useLibrary();
  const versions = useVersions();
  const error = library.error ?? versions.error;

  return (
    <div className="shell">
      <header className="top-bar">
        <span className="wordmark">PneuText</span>
      </header>
      <main className="stage">
        {error ? (
          <div role="alert" className="notice">
            <p>{error.message}</p>
            <button
              type="button"
              onClick={() => {
                void library.refetch();
                void versions.refetch();
              }}
            >
              Try again
            </button>
          </div>
        ) : versions.data === undefined ? (
          <p className="quiet">Opening the library…</p>
        ) : versions.data.length === 0 ? (
          <section className="empty-page" aria-labelledby="empty-title">
            <h1 id="empty-title">This library is empty</h1>
            <p>Import a paged corpus to begin reading and annotating.</p>
            <Link className="button" to="/import">
              Import a corpus
            </Link>
          </section>
        ) : (
          <section className="panel" aria-labelledby="library-title">
            <h1 id="library-title">Library</h1>
            <VersionList versions={versions.data} />
            <Link className="button" to="/import">
              Import a corpus
            </Link>
          </section>
        )}
      </main>
      {library.data && (
        <footer className="status-bar quiet">
          PneuText {library.data.app_version} · library schema {library.data.schema_version}
        </footer>
      )}
    </div>
  );
}
