import { useLibrary } from "./api/queries";
import { LibraryHome } from "./LibraryHome";

export function App() {
  const library = useLibrary();
  if (library.isPending) return <LibraryHome state="loading" />;
  if (library.isError) {
    return (
      <LibraryHome
        state="error"
        message={library.error.message}
        onRetry={() => void library.refetch()}
      />
    );
  }
  return <LibraryHome state="ready" library={library.data} />;
}
