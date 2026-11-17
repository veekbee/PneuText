-- The legacy commentary also uses the prefix `i` for notes of interpretation.
-- Added only where no type already has that code or name.
INSERT INTO note_type (name, code, color, sort, role)
SELECT 'Interpretation', 'i', '#b58aa5', 55, 'note'
WHERE NOT EXISTS (
    SELECT 1 FROM note_type WHERE code = 'i' OR LOWER(name) = 'interpretation'
);
