// The app's URLs. Every page and line has a stable address:
//   /v/{version_id}/p/{page}  and  /v/{version_id}/p/{page}#l{line_no}

export type Route =
  | { name: "home" }
  | { name: "import" }
  | { name: "page"; versionId: number; page: number; line: number | null }
  | { name: "not-found" };

const PAGE_PATH = /^\/v\/(\d+)\/p\/(\d+)\/?$/;
const LINE_HASH = /^#l(\d+)$/;

export function parseRoute(pathname: string, hash = ""): Route {
  if (pathname === "/" || pathname === "") return { name: "home" };
  if (pathname === "/import" || pathname === "/import/") return { name: "import" };
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

export function pagePath(versionId: number, page: number, line?: number | null): string {
  const base = `/v/${versionId}/p/${page}`;
  return line == null ? base : `${base}#l${line}`;
}
