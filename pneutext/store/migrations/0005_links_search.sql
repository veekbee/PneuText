-- Cross-references, and full-text search over the corpus and over note bodies.

-- A cross-reference. Its source is a note (a reference written in the note's body) or a
-- passage (a link made passage to passage); its target is a note or a passage.
CREATE TABLE link (
    id                   INTEGER PRIMARY KEY,
    source_annotation_id INTEGER REFERENCES annotation (id) ON DELETE CASCADE,
    source_anchor_id     INTEGER REFERENCES anchor (id) ON DELETE CASCADE,
    target_annotation_id INTEGER REFERENCES annotation (id) ON DELETE CASCADE,
    target_anchor_id     INTEGER REFERENCES anchor (id) ON DELETE CASCADE,
    relation             TEXT NOT NULL DEFAULT 'reference',
    origin               TEXT NOT NULL CHECK (origin IN ('inline', 'manual')),
    CHECK ((source_annotation_id IS NULL) != (source_anchor_id IS NULL)),
    CHECK ((target_annotation_id IS NULL) != (target_anchor_id IS NULL))
) STRICT;

CREATE INDEX link_source_annotation ON link (source_annotation_id);
CREATE INDEX link_target_annotation ON link (target_annotation_id);
CREATE INDEX link_source_anchor ON link (source_anchor_id);
CREATE INDEX link_target_anchor ON link (target_anchor_id);

-- Search follows the text: the corpus index is kept in step by triggers on `segment`,
-- not by import code, so later edits to the text re-index themselves.
CREATE VIRTUAL TABLE segment_fts USING fts5(
    text, content = 'segment', content_rowid = 'id', tokenize = 'unicode61 remove_diacritics 2'
);

INSERT INTO segment_fts (rowid, text) SELECT id, text FROM segment;

CREATE TRIGGER segment_fts_insert AFTER INSERT ON segment BEGIN
    INSERT INTO segment_fts (rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER segment_fts_delete AFTER DELETE ON segment BEGIN
    INSERT INTO segment_fts (segment_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER segment_fts_update AFTER UPDATE OF text ON segment BEGIN
    INSERT INTO segment_fts (segment_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO segment_fts (rowid, text) VALUES (new.id, new.text);
END;

CREATE VIRTUAL TABLE note_fts USING fts5(
    body_md, content = 'annotation', content_rowid = 'id',
    tokenize = 'unicode61 remove_diacritics 2'
);

INSERT INTO note_fts (rowid, body_md) SELECT id, body_md FROM annotation;

CREATE TRIGGER note_fts_insert AFTER INSERT ON annotation BEGIN
    INSERT INTO note_fts (rowid, body_md) VALUES (new.id, new.body_md);
END;

CREATE TRIGGER note_fts_delete AFTER DELETE ON annotation BEGIN
    INSERT INTO note_fts (note_fts, rowid, body_md) VALUES ('delete', old.id, old.body_md);
END;

CREATE TRIGGER note_fts_update AFTER UPDATE OF body_md ON annotation BEGIN
    INSERT INTO note_fts (note_fts, rowid, body_md) VALUES ('delete', old.id, old.body_md);
    INSERT INTO note_fts (rowid, body_md) VALUES (new.id, new.body_md);
END;
