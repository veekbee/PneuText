-- The corpus: works, their versions, the text as segments, and print pagination over it.

CREATE TABLE work (
    id     INTEGER PRIMARY KEY,
    code   TEXT NOT NULL UNIQUE,   -- short name used in references
    title  TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT ''
) STRICT;

CREATE TABLE version (
    id            INTEGER PRIMARY KEY,
    work_id       INTEGER NOT NULL REFERENCES work (id) ON DELETE CASCADE,
    label         TEXT NOT NULL,
    language      TEXT NOT NULL DEFAULT '',
    source_format TEXT NOT NULL,
    content_hash  TEXT NOT NULL,   -- fingerprint of the imported files, not of the current text
    imported_at   TEXT NOT NULL,
    edit_seq      INTEGER NOT NULL DEFAULT 0   -- counts edits to this version's text
) STRICT;

CREATE INDEX version_content_hash ON version (content_hash);

-- One paragraph, or one piece of page furniture. Identity is `id`, never `position`.
CREATE TABLE segment (
    id          INTEGER PRIMARY KEY,
    version_id  INTEGER NOT NULL REFERENCES version (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,   -- sparse reading order
    kind        TEXT NOT NULL
                CHECK (kind IN ('paragraph', 'synopsis', 'chapter_number', 'ornament', 'rule')),
    text        TEXT NOT NULL,      -- NFC; one space where a print line break fell
    changed_seq INTEGER NOT NULL DEFAULT 0,
    UNIQUE (version_id, position)
) STRICT;

CREATE TABLE division (
    id               INTEGER PRIMARY KEY,
    version_id       INTEGER NOT NULL REFERENCES version (id) ON DELETE CASCADE,
    kind             TEXT NOT NULL,
    label            TEXT NOT NULL,
    first_segment_id INTEGER NOT NULL REFERENCES segment (id) ON DELETE CASCADE
) STRICT;

CREATE INDEX division_version ON division (version_id);

-- One print edition's page and line breaks over a version's segments.
CREATE TABLE pagination (
    id         INTEGER PRIMARY KEY,
    version_id INTEGER NOT NULL REFERENCES version (id) ON DELETE CASCADE,
    label      TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1))
) STRICT;

CREATE UNIQUE INDEX pagination_one_default ON pagination (version_id) WHERE is_default = 1;

-- One print line. It ends where the next line of its segment starts.
CREATE TABLE line (
    id            INTEGER PRIMARY KEY,
    pagination_id INTEGER NOT NULL REFERENCES pagination (id) ON DELETE CASCADE,
    segment_id    INTEGER NOT NULL REFERENCES segment (id) ON DELETE CASCADE,
    start_offset  INTEGER NOT NULL CHECK (start_offset >= 0),   -- in code points
    page          INTEGER NOT NULL,
    line_no       INTEGER,   -- numbered among the page's text lines; NULL for furniture
    UNIQUE (pagination_id, segment_id, start_offset)
) STRICT;

CREATE INDEX line_page ON line (pagination_id, page);
CREATE INDEX line_segment ON line (segment_id);
