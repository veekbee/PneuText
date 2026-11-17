-- Narrative time: the time a time mention denotes.
--
-- A time mention with no row here has not been given a value yet. The resolved date of
-- a point is computed by walking the chain of offsets and is never stored.
CREATE TABLE time_point (
    mention_id     INTEGER PRIMARY KEY REFERENCES mention (id) ON DELETE CASCADE,
    kind           TEXT NOT NULL CHECK (kind IN ('absolute', 'offset')),
    at             TEXT,     -- ISO 8601 date or date-time, at whatever precision is known
    "offset"       TEXT,     -- ISO 8601 duration, such as P5D
    relative_to_id INTEGER REFERENCES time_point (mention_id) ON DELETE SET NULL,
    label          TEXT,     -- a name later points can count from
    remark         TEXT NOT NULL DEFAULT '',   -- for an approximate time, in the author's words
    CHECK (
        (kind = 'absolute' AND at IS NOT NULL AND "offset" IS NULL AND relative_to_id IS NULL)
        OR (kind = 'offset' AND "offset" IS NOT NULL AND at IS NULL)
    )
) STRICT;

CREATE INDEX time_point_label ON time_point (label);
