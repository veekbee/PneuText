-- Library-level key/value facts (for example, when the library was created).
CREATE TABLE library_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

INSERT INTO library_meta (key, value)
VALUES ('created_at', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
