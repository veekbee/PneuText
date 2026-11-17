-- Notes: anchors into the text, note types, annotations and tags.
-- Annotations are stand-off data: they point into segments and never change them.

-- A span of text. It knows nothing of pages or lines. The end is exclusive.
CREATE TABLE anchor (
    id               INTEGER PRIMARY KEY,
    version_id       INTEGER NOT NULL REFERENCES version (id) ON DELETE CASCADE,
    start_segment_id INTEGER NOT NULL REFERENCES segment (id) ON DELETE CASCADE,
    start_offset     INTEGER NOT NULL CHECK (start_offset >= 0),   -- in code points
    end_segment_id   INTEGER NOT NULL REFERENCES segment (id) ON DELETE CASCADE,
    end_offset       INTEGER NOT NULL CHECK (end_offset >= 0),
    exact            TEXT NOT NULL,   -- the quoted text, for re-locating after an edit
    prefix           TEXT NOT NULL,   -- up to 32 characters of context before
    suffix           TEXT NOT NULL,   -- and after
    resolved_seq     INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'orphaned'))
) STRICT;

CREATE INDEX anchor_version ON anchor (version_id);
CREATE INDEX anchor_start ON anchor (start_segment_id);
CREATE INDEX anchor_end ON anchor (end_segment_id);

-- A note category. Types are data: the author can add, rename, recolor and merge them.
CREATE TABLE note_type (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    code  TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL,
    sort  INTEGER NOT NULL,
    role  TEXT NOT NULL DEFAULT 'note'
          CHECK (role IN ('note', 'definition', 'chapter_title', 'chapter_summary'))
) STRICT;

-- The types a new library starts with. Muted, and distinct in lightness as well as hue
-- so they stay apart when overlapped or printed in gray.
INSERT INTO note_type (name, code, color, sort, role) VALUES
    ('Clarification',   'cl', '#7d9bbd', 10, 'note'),
    ('Comment',         'c',  '#d9b44a', 20, 'note'),
    ('Historical',      'h',  '#a5673f', 30, 'note'),
    ('Meditation',      'm',  '#8f7ab8', 40, 'note'),
    ('Literary',        'l',  '#6fa287', 50, 'note'),
    ('Spanish',         's',  '#c9705f', 60, 'note'),
    ('Definition',      'd',  '#4f7f86', 70, 'definition'),
    ('Chapter title',   'ct', '#8a8a8a', 80, 'chapter_title'),
    ('Chapter summary', 'cs', '#b0b0b0', 90, 'chapter_summary');

-- A note. An empty body is a bare highlight.
CREATE TABLE annotation (
    id         INTEGER PRIMARY KEY,
    anchor_id  INTEGER NOT NULL UNIQUE REFERENCES anchor (id) ON DELETE CASCADE,
    type_id    INTEGER NOT NULL REFERENCES note_type (id),
    scope      TEXT NOT NULL DEFAULT 'span' CHECK (scope IN ('span', 'page', 'chapter')),
    level      INTEGER NOT NULL DEFAULT 1 CHECK (level IN (1, 2)),
    body_md    TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ready')),
    legacy_id  TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX annotation_type ON annotation (type_id);

CREATE TABLE tag (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE annotation_tag (
    annotation_id INTEGER NOT NULL REFERENCES annotation (id) ON DELETE CASCADE,
    tag_id        INTEGER NOT NULL REFERENCES tag (id) ON DELETE CASCADE,
    PRIMARY KEY (annotation_id, tag_id)
) STRICT, WITHOUT ROWID;
