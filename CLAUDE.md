# PneuText

A local, single-user research workbench for close reading: a Python (FastAPI + SQLite)
server with a React/TypeScript front end. The design brief is `claude/pneutext-design.md`
(kept locally, git-ignored). Build what it states, in its milestone order.

## Commands

| Task | Command |
| --- | --- |
| Run the app | `cd frontend && npm run build`, then `uv run pneutext` (`--library DIR`, `--port N`, `--no-browser`) |
| Front-end dev server | `uv run pneutext --no-browser` and, in `frontend/`, `npm run dev` (proxies `/api` to port 8765) |
| Backend tests | `uv run pytest` |
| Backend lint | `uv run ruff check .` and `uv run ruff format --check .` |
| Front-end tests | `cd frontend && npm test` |
| Front-end lint and types | `cd frontend && npm run lint && npm run typecheck` |
| Regenerate API types | `cd frontend && npm run gen:api` (after any route or schema change) |

## Rules that are easy to break

- No corpus text from any real work in the repository, fixtures, logs, error messages or
  commit messages. Log ids, pages and line numbers, never text. Fixtures are invented prose.
- Nothing in the code names or special-cases a particular book; work codes, note types,
  categories, file-name patterns and LaTeX conversions are data or configuration.
- SQL appears only in `pneutext/store/`. Schema changes are new numbered files in
  `pneutext/store/migrations/`; never edit an applied one.
- Routers call services and never touch SQL. The server never renders HTML.
- Blank mode and every publishable export read only the shape projection, which has no text.
- Front-end components reach the server only through `frontend/src/api`; its types are
  generated (`schema.d.ts`), never hand-written. Text is rendered as React text nodes only.
- The server binds to `127.0.0.1` only; the app makes no network requests beyond the local API.
- Each milestone ends with tests passing, `ruff` and ESLint clean, and a commit pushed to `main`.

## Toolchain notes

- TypeScript is pinned to 5.9 because `openapi-typescript` 7 requires TypeScript 5.
- Playwright is not set up yet; it arrives with the first end-to-end test.
