-- Export profiles: which notes an edition includes. Saved, so a first-reading edition
-- and a full edition can both be produced; shared by the monograph and the web edition.
CREATE TABLE export_profile (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    type_ids TEXT,            -- JSON list of note type ids; NULL means every type
    levels   TEXT NOT NULL,   -- JSON list of reading levels, such as [1] or [1, 2]
    statuses TEXT NOT NULL    -- JSON list of statuses, such as ["ready"]
) STRICT;

-- By default only notes that are ready are published.
INSERT INTO export_profile (name, type_ids, levels, statuses) VALUES
    ('First reading', NULL, '[1]', '["ready"]'),
    ('Full edition', NULL, '[1, 2]', '["ready"]');
