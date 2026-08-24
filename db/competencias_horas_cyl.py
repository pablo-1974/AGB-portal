"""Horas semanales curriculares CyL (ESO Anexo V / Decreto 39/2022).

Se usa solo si el catálogo Neon no tiene horas para esa materia.
"""

from __future__ import annotations

from db.enrolled_subject_catalog import competencias_materia_group_key

# (curso, materia_key) → periodos lectivos semanales
_HORAS_ESO: dict[tuple[int, str], int] = {}
_HORAS_BACH: dict[tuple[int, str], int] = {}


def _key(nombre: str) -> str:
    return competencias_materia_group_key(nombre) or (nombre or "").strip().lower()


def _eso(curso: int, nombre: str, horas: int) -> None:
    _HORAS_ESO[(int(curso), _key(nombre))] = int(horas)


def _bach(curso: int, nombre: str, horas: int) -> None:
    _HORAS_BACH[(int(curso), _key(nombre))] = int(horas)


# --- ESO 1º (Anexo V) ---
_eso(1, "Biología y Geología", 3)
_eso(1, "Educación Física", 2)
_eso(1, "Educación Plástica, Visual y Audiovisual", 3)
_eso(1, "Geografía e Historia", 3)
_eso(1, "Lengua Castellana y Literatura", 4)
_eso(1, "Lengua Extranjera", 4)
_eso(1, "Inglés", 4)
_eso(1, "Matemáticas", 4)
_eso(1, "Tecnología y Digitalización", 3)
_eso(1, "Segunda Lengua Extranjera: Francés", 2)
_eso(1, "Conocimiento del Lenguaje", 2)
_eso(1, "Conocimiento de las Matemáticas", 2)
_eso(1, "Religión Católica", 1)
_eso(1, "Religión Evangélica", 1)
_eso(1, "Religión Islámica", 1)
_eso(1, "Medidas de Atención Educativa", 1)

# --- ESO 2º ---
_eso(2, "Educación Física", 2)
_eso(2, "Física y Química", 3)
_eso(2, "Geografía e Historia", 3)
_eso(2, "Lengua Castellana y Literatura", 4)
_eso(2, "Lengua Extranjera", 3)
_eso(2, "Inglés", 3)
_eso(2, "Matemáticas", 4)
_eso(2, "Música", 3)
_eso(2, "Segunda Lengua Extranjera: Francés", 2)
_eso(2, "Conocimiento del Lenguaje", 2)
_eso(2, "Conocimiento de las Matemáticas", 2)
_eso(2, "Cultura Clásica", 2)
_eso(2, "Religión Católica", 2)
_eso(2, "Religión Evangélica", 2)
_eso(2, "Religión Islámica", 2)
_eso(2, "Medidas de Atención Educativa", 2)

# --- ESO 3º ---
_eso(3, "Biología y Geología", 2)
_eso(3, "Educación en Valores Cívicos y Éticos", 1)
_eso(3, "Educación Física", 2)
_eso(3, "Educación Plástica, Visual y Audiovisual", 3)
_eso(3, "Física y Química", 2)
_eso(3, "Geografía e Historia", 3)
_eso(3, "Lengua Castellana y Literatura", 4)
_eso(3, "Lengua Extranjera", 3)
_eso(3, "Inglés", 3)
_eso(3, "Matemáticas", 4)
_eso(3, "Música", 3)
_eso(3, "Tecnología y Digitalización", 2)
_eso(3, "Segunda Lengua Extranjera: Francés", 2)
_eso(3, "Conocimiento del Lenguaje", 2)
_eso(3, "Conocimiento de las Matemáticas", 2)
_eso(3, "Control y Robótica", 2)
_eso(3, "Iniciación a la Actividad Emprendedora y Empresarial", 2)
_eso(3, "Taller de Artes Plásticas", 2)
_eso(3, "Taller de Expresión Musical", 2)
_eso(3, "Religión Católica", 1)
_eso(3, "Religión Evangélica", 1)
_eso(3, "Religión Islámica", 1)
_eso(3, "Medidas de Atención Educativa", 1)
# Diversificación: suma de las materias que integra el ámbito (art. 19.5).
_eso(3, "Ámbito lingüístico y social", 7)
_eso(3, "Ámbito científico-tecnológico", 8)
_eso(3, "Ámbito Práctico", 2)

# --- ESO 4º ---
_eso(4, "Educación Física", 2)
_eso(4, "Geografía e Historia", 3)
_eso(4, "Lengua Castellana y Literatura", 4)
_eso(4, "Lengua Extranjera", 3)
_eso(4, "Inglés", 3)
_eso(4, "Matemáticas A", 4)
_eso(4, "Matemáticas B", 4)
_eso(4, "Biología y Geología", 4)
_eso(4, "Latín", 4)
_eso(4, "Economía y Emprendimiento", 4)
_eso(4, "Física y Química", 4)
_eso(4, "Digitalización", 2)
_eso(4, "Expresión Artística", 2)
_eso(4, "Formación y Orientación Personal y Profesional", 2)
_eso(4, "Música", 2)
_eso(4, "Segunda Lengua Extranjera: Francés", 2)
_eso(4, "Tecnología", 2)
_eso(4, "Conocimiento del Lenguaje", 2)
_eso(4, "Conocimiento de las Matemáticas", 2)
_eso(4, "Cultura Científica", 2)
_eso(4, "Cultura Clásica", 2)
_eso(4, "Educación Financiera", 2)
_eso(4, "Formación para la Empresa y el Empleo", 2)
_eso(4, "Geografía Económica", 2)
_eso(4, "Laboratorio de Ciencias", 2)
_eso(4, "Literatura Universal", 2)
_eso(4, "Programación Informática", 2)
_eso(4, "Resolución de Problemas", 2)
_eso(4, "Taller de Filosofía", 2)
_eso(4, "Religión Católica", 1)
_eso(4, "Religión Evangélica", 1)
_eso(4, "Religión Islámica", 1)
_eso(4, "Medidas de Atención Educativa", 1)
_eso(4, "Ámbito lingüístico y social", 7)
_eso(4, "Ámbito científico-tecnológico", 8)
_eso(4, "Ámbito Práctico", 2)

# Bachillerato: el catálogo ya trae horas; solo huecos puntuales.
_bach(2, "Historia de la Música y de la Danza", 4)


def horas_curriculares(
    *,
    etapa: str,
    curso: int,
    materia_key: str,
) -> int | None:
    """Horas semanales oficiales si el catálogo no las tiene."""
    stage = (etapa or "").strip().lower()
    key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    if not key:
        return None
    curso_n = int(curso)
    if stage == "eso":
        found = _HORAS_ESO.get((curso_n, key))
        if found is not None:
            return found
        if key.startswith("religion") or key.startswith("medidas de atencion"):
            return 2 if curso_n == 2 else 1
        if key.startswith("ambito linguistico"):
            return 7
        if key.startswith("ambito cientifico"):
            return 8
        if key.startswith("ambito practico"):
            return 2
        return None
    if stage == "bach":
        return _HORAS_BACH.get((curso_n, key))
    return None
