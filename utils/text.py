import re
import unicodedata


def normalize_for_sort(text: str) -> str:
    """
    Normaliza para ordenar como en español: ignora mayúsculas/minúsculas y tildes (á≈a).
    """
    if not text:
        return ""

    normalized = unicodedata.normalize("NFD", text)
    without_accents = "".join(
        c for c in normalized if unicodedata.category(c) != "Mn"
    )

    return without_accents.casefold()


def normalize_alumno_key(name: str) -> str:
    """Clave estable de alumno: espacios colapsados, coma canónica, casefold.

    Une variantes típicas de importación («APELLIDOS , NOMBRE» vs «APELLIDOS, NOMBRE»).
    """
    s = " ".join((name or "").split())
    s = re.sub(r"\s*,\s*", ", ", s)
    s = " ".join(s.split())
    return s.casefold()


def sql_alumno_key(column_sql: str) -> str:
    """Expresión SQL equivalente a ``normalize_alumno_key`` (PostgreSQL)."""
    col = (column_sql or "").strip()
    if not col:
        raise ValueError("column_sql vacío")
    return (
        "regexp_replace("
        f"regexp_replace(LOWER(TRIM({col})), '\\s+', ' ', 'g'), "
        "'\\s*,\\s*', ', ', 'g')"
    )
