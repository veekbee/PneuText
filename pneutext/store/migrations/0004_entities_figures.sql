-- Entities and their mentions in the text, figures, and a record of what a legacy
-- commentary import produced.

-- An author-defined category of entity. Categories are data, like note types.
CREATE TABLE entity_category (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    color   TEXT NOT NULL,
    sort    INTEGER NOT NULL,
    is_time INTEGER NOT NULL DEFAULT 0 CHECK (is_time IN (0, 1))
) STRICT;

INSERT INTO entity_category (name, color, sort, is_time) VALUES
    ('places',  '#5b8c85', 10, 0),
    ('animals', '#b07a4a', 20, 0),
    ('plants',  '#7a9a52', 30, 0),
    ('numbers', '#7f7aa8', 40, 0),
    ('time',    '#a86a7a', 50, 1);

-- Something indexed: a place, an animal, a number.
CREATE TABLE entity (
    id          INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES entity_category (id),
    name        TEXT NOT NULL,
    value       TEXT,   -- a normalized form, such as 46
    UNIQUE (category_id, name)
) STRICT;

-- One occurrence in the text. A time mention has no entity; its category says what it is.
CREATE TABLE mention (
    id          INTEGER PRIMARY KEY,
    anchor_id   INTEGER NOT NULL UNIQUE REFERENCES anchor (id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES entity_category (id),
    entity_id   INTEGER REFERENCES entity (id)
) STRICT;

CREATE INDEX mention_entity ON mention (entity_id);
CREATE INDEX mention_category ON mention (category_id);

-- An image in the library's figures/ folder.
CREATE TABLE figure (
    id      INTEGER PRIMARY KEY,
    label   TEXT NOT NULL UNIQUE,
    file    TEXT NOT NULL,
    caption TEXT NOT NULL DEFAULT '',
    credit  TEXT NOT NULL DEFAULT ''
) STRICT;

-- What a legacy commentary file produced, so that importing the page again replaces
-- exactly those notes and mentions and leaves ones made in the app alone.
CREATE TABLE legacy_item (
    id            INTEGER PRIMARY KEY,
    version_id    INTEGER NOT NULL REFERENCES version (id) ON DELETE CASCADE,
    page          INTEGER NOT NULL,
    annotation_id INTEGER REFERENCES annotation (id) ON DELETE CASCADE,
    mention_id    INTEGER REFERENCES mention (id) ON DELETE CASCADE,
    CHECK ((annotation_id IS NULL) != (mention_id IS NULL))
) STRICT;

CREATE INDEX legacy_item_page ON legacy_item (version_id, page);
