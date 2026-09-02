-- Todo profesor que conste como sustituto en leaves (is_substitution) no es titular de plaza en este modelo.

BEGIN;

UPDATE users u
SET titular = FALSE
WHERE EXISTS (
    SELECT 1 FROM leaves l
    WHERE l.teacher_id = u.id AND l.is_substitution IS TRUE
);

COMMIT;
