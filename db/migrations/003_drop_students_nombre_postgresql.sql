-- =====================================================================
-- Neon / PostgreSQL: eliminar columna redundante students.nombre
--
-- La aplicación de incidencias identifica al alumno solo con students.alumno
-- (junto con grupo). La columna nombre era opcional y duplicaba información.
--
-- Ejecutar en el SQL Editor de Neon (o psql) DESPUÉS de una copia de seguridad.
-- Orden recomendado:
--   1) Backup / export de tabla students
--   2) Ejecutar este script
--   3) Desplegar el código actualizado que ya no referencia nombre
-- =====================================================================

-- Caso residual: alumno en blanco pero nombre informado → copiar a alumno
UPDATE students
SET alumno = trim(nombre)
WHERE trim(alumno) = ''
  AND nombre IS NOT NULL
  AND trim(nombre) <> '';

-- Eliminar columna
ALTER TABLE students DROP COLUMN IF EXISTS nombre;

COMMENT ON COLUMN students.alumno IS
    'Nombre del alumno (único campo de nombre; usado por incidencias y listados).';
