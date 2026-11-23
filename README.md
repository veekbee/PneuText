# PneuText

A local research workbench for close reading of existing texts: annotate passages,
cross-reference them, tag what they mention, and publish the result.

PneuText runs on your own machine: a Python server with a browser interface, keeping
everything in one SQLite file. It is single-user and makes no network calls.

## What it does

- **Reads a paged corpus.** One text file per print page, one print line per line. Pages,
  lines, paragraphs and chapter openings are kept.
- **Shows each page two ways.** *Text mode* shows the words. *Blank mode* keeps the page's
  shape but draws every line as an empty bar, with highlights where notes attach.
- **Typed notes on any span**, including spans that nest or overlap, with a reading level
  (first reading, or for readers who know the whole book) and a status (draft or ready).
- **Cross-references** from a note to a page, a passage or another note, with backlinks at
  the target; passage-to-passage links.
- **Entities** in categories you define, browsable as an index; **narrative time**, where
  each time mention resolves to a date by walking a chain of offsets.
- **Figures**, editorial to-dos, a review view with bulk status changes, full-text search.
- **Exports a monograph** as a LaTeX project: blank page facsimiles with numbered
  highlights, the notes, a glossary, indexes and a list of figures.

Two rules shape it. Annotations are stand-off data: they point into the text and never
change it. And corpus text never leaks: blank mode and every publishable export are built
from data that contains no corpus text at all, so a commentary can be published without
the work it comments on.

## Requirements

- Python 3.12 or newer, and [uv](https://docs.astral.sh/uv/)
- Node.js 22 or newer (to build the interface)
- Optional, for building the monograph PDF: `latexmk` with LuaLaTeX, or Tectonic

## Run it

```sh
cd frontend && npm install && npm run build && cd ..
uv run pneutext
```

This opens the app in your browser. The library lives in `~/.pneutext/` (a database and a
`figures/` folder) unless you pass `--library DIR`. Other options: `--port N`,
`--no-browser`.

To start, choose **Import a corpus** and give the folder that holds your page files. File
names carry the page number (by default `…_corp_p045.txt`); the pattern can be changed
in the form. Blank lines separate paragraphs. A file that does not end with a blank line
runs its last paragraph on to the next page.

When you correct a page file, or add pages at the end, choose **Update the text** beside
the work on the library page and give the same folder. The files are compared with the
stored text and only what differs is changed. The check comes first and lists the pages
affected. This works only while the text has no notes, mentions or links: once something
is marked on it, a change made outside PneuText could move it unseen, so the update is
refused. Paragraphs must stay the same in number and order: to add, remove, split or
join paragraphs, import the folder again as a new text.

## Keys

| Key | Action |
| --- | --- |
| `←` `→` | Previous and next page |
| `g` | Go to page |
| `/` | Search |
| `b` | Switch between text and blank mode |
| `n` | New note on the selection |
| `h` | Bare highlight on the selection |
| `e` | Tag the selection as an entity or a time |
| `l` | Start a link from the selection, or complete one |
| `Esc` | Dismiss the popover, or cancel the link in progress |

## Note syntax

A note body is Markdown, plus:

| Form | Meaning |
| --- | --- |
| `{{ab:292}}`, `{{ab:292-293}}`, `{{ab:45.12}}` | A page, a page range, or a line of the work with code `ab` |
| `{{note:123}}` | Another note |
| `![Caption](fig:label)` | Place a figure here |
| `{{fig:label}}` | Refer to a figure |
| `{{gloss:word\|meaning}}` | A foreign word with its translation |
| `{{when}}` | The narrative date at the note's place in the text |
| `{{since:label}}` | Time elapsed there since the time point with that label |
| A paragraph starting `TODO:` | An editorial remark: listed among the to-dos, never exported |

## Development

```sh
uv run pytest                      # backend tests
uv run ruff check . && uv run ruff format --check .
cd frontend
npm test                           # unit tests
npm run lint && npm run typecheck
npm run e2e                        # browser tests against the real server
npm run gen:api                    # regenerate API types after a route or schema change
```

For interface work, run `uv run pneutext --no-browser` and, in `frontend/`, `npm run dev`.

```
pneutext/
  core/        dataclasses, references, anchors, page shape, narrative time; no I/O
  notes/       note-body parser: Markdown plus PneuText's forms, to a syntax tree
  importers/   paged corpus; legacy commentary
  store/       SQLite access and migrations; the only code that writes SQL
  services/    import, annotate, link, search, review, export
  export/      monograph (LaTeX) and backup (JSON) writers; never imports the store
  api/         FastAPI routers and schemas, all under /api
frontend/      React and TypeScript interface (Vite)
tests/         pytest, with an invented fixture book
```

Tests use an invented fixture book. No text from any real work belongs in this
repository, its fixtures, its logs or its commit messages.
