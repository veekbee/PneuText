// The app's URLs. Every page and line has a stable address:
//   /v/{version_id}/p/{page}  and  /v/{version_id}/p/{page}#l{line_no}

export const VIEWS = [
  "review",
  "todo",
  "entities",
  "chronology",
  "figures",
  "types",
  "export",
] as const;
export type ViewName = (typeof VIEWS)[number];

export type Route =
  | { name: "home" }
  | { name: "import" }
  | { name: "page"; versionId: number; page: number; line: number | null }
  | { name: "import-commentary"; versionId: number }
  | { name: "view"; versionId: number; view: ViewName }
  | { name: "not-found" };

const PAGE_PATH = /^\/v\/(\d+)\/p\/(\d+)\/?$/;
const COMMENTARY_PATH = /^\/v\/(\d+)\/import-commentary\/?$/;
const VIEW_PATH = /^\/v\/(\d+)\/([a-z]+)\/?$/;
const LINE_HASH = /^#l(\d+)$/;

export function parseRoute(pathname: string, hash = ""): Route {
  if (pathname === "/" || pathname === "") return { name: "home" };
  if (pathname === "/import" || pathname === "/import/") return { name: "import" };
  const commentary = COMMENTARY_PATH.exec(pathname);
  if (commentary !== null) return { name: "import-commentary", versionId: Number(commentary[1]) };
  const view = VIEW_PATH.exec(pathname);
  if (view !== null && (VIEWS as readonly string[]).includes(view[2] as string)) {
    return { name: "view", versionId: Number(view[1]), view: view[2] as ViewName };
  }
  const match = PAGE_PATH.exec(pathname);
  if (match !== null) {
    const line = LINE_HASH.exec(hash);
    return {
      name: "page",
      versionId: Number(match[1]),
      page: Number(match[2]),
      line: line === null ? null : Number(line[1]),
    };
  }
  return { name: "not-found" };
}

export function commentaryImportPath(versionId: number): string {
  return `/v/${versionId}/import-commentary`;
}

export function viewPath(versionId: number, view: ViewName): string {
  return `/v/${versionId}/${view}`;
}

export function pagePath(versionId: number, page: number, line?: number | null): string {
  const base = `/v/${versionId}/p/${page}`;
  return line == null ? base : `${base}#l${line}`;
}
