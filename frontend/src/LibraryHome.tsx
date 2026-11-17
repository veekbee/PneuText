import type { LibraryInfo } from "./api/client";

export type LibraryHomeProps =
  | { state: "loading" }
  | { state: "error"; message: string; onRetry: () => void }
  | { state: "ready"; library: LibraryInfo };

// Takes plain data and never calls the API itself.
export function LibraryHome(props: LibraryHomeProps) {
  return (
    <div className="shell">
      <header className="top-bar">
        <h1 className="wordmark">PneuText</h1>
      </header>
      <main className="stage">
        {props.state === "loading" && <p className="quiet">Opening the library…</p>}
        {props.state === "error" && (
          <div role="alert" className="notice">
            <p>{props.message}</p>
            <button type="button" onClick={props.onRetry}>
              Try again
            </button>
          </div>
        )}
        {props.state === "ready" && (
          <section className="empty-page" aria-labelledby="empty-title">
            <h2 id="empty-title">This library is empty</h2>
            <p>Import a paged corpus to begin reading and annotating.</p>
          </section>
        )}
      </main>
      {props.state === "ready" && (
        <footer className="status-bar quiet">
          PneuText {props.library.app_version} · library schema {props.library.schema_version}
        </footer>
      )}
    </div>
  );
}
