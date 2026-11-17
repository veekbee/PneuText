import { ImportCorpus } from "./library/ImportCorpus";
import { LibraryHome } from "./library/LibraryHome";
import { Reader } from "./page/Reader";
import { Link, useRoute } from "./router";

export function App() {
  const route = useRoute();
  switch (route.name) {
    case "home":
      return <LibraryHome />;
    case "import":
      return <ImportCorpus />;
    case "page":
      return <Reader versionId={route.versionId} page={route.page} line={route.line} />;
    case "not-found":
      return (
        <div className="shell">
          <header className="top-bar">
            <span className="wordmark">PneuText</span>
          </header>
          <main className="stage">
            <div role="alert" className="notice">
              <p>There is nothing at this address.</p>
              <Link to="/">Back to the library</Link>
            </div>
          </main>
        </div>
      );
  }
}
