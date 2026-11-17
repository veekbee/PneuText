import { ChronologyView } from "./entities/ChronologyView";
import { EntitiesView } from "./entities/EntitiesView";
import { FiguresView } from "./figures/FiguresView";
import { ImportCommentary } from "./library/ImportCommentary";
import { ImportCorpus } from "./library/ImportCorpus";
import { LibraryHome } from "./library/LibraryHome";
import { TypesView } from "./notes/TypesView";
import { Reader } from "./page/Reader";
import { ReviewView } from "./review/ReviewView";
import { TodoView } from "./review/TodoView";
import { Link, useRoute } from "./router";

export function App() {
  const route = useRoute();
  switch (route.name) {
    case "home":
      return <LibraryHome />;
    case "import":
      return <ImportCorpus />;
    case "import-commentary":
      return <ImportCommentary versionId={route.versionId} />;
    case "view":
      switch (route.view) {
        case "review":
          return <ReviewView versionId={route.versionId} />;
        case "todo":
          return <TodoView versionId={route.versionId} />;
        case "entities":
          return <EntitiesView versionId={route.versionId} />;
        case "chronology":
          return <ChronologyView versionId={route.versionId} />;
        case "figures":
          return <FiguresView versionId={route.versionId} />;
        case "types":
          return <TypesView versionId={route.versionId} />;
      }
    // eslint-disable-next-line no-fallthrough -- every view returns above
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
