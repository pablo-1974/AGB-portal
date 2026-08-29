"""Catálogo de departamentos (nombre, abreviatura, jefe)."""

from __future__ import annotations

import unicodedata
from typing import Any

from db.connection import get_db
from utils.enums import ROLES_ADMINISTRATIVOS
from utils.text import normalize_for_sort

_schema_ready = False


def ensure_departamentos_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS departamentos (
                    abreviatura TEXT PRIMARY KEY,
                    departamento TEXT NOT NULL,
                    jefe TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                ALTER TABLE departamentos
                ADD COLUMN IF NOT EXISTS jefe TEXT
                """
            )
            cur.execute(
                """
                ALTER TABLE departamentos
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
                """
            )
            cur.execute(
                """
                UPDATE departamentos
                SET updated_at = NOW()
                WHERE updated_at IS NULL
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_departamentos_nombre_lower
                ON departamentos (LOWER(BTRIM(departamento)))
                """
            )
    _schema_ready = True


def _norm_header(value: object) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return " ".join(text.split())


def _cell_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_departamentos_workbook(wb) -> list[dict[str, str]]:
    """Lee filas con cabeceras Departamento / abreviatura / Jefe."""
    ws = wb.active
    headers = [_norm_header(c.value) for c in ws[1]]
    idx = {name: pos for pos, name in enumerate(headers) if name}

    dep_idx = next(
        (
            idx[k]
            for k in ("departamento", "nombre", "name", "departamento nombre")
            if k in idx
        ),
        None,
    )
    abr_idx = next(
        (
            idx[k]
            for k in ("abreviatura", "abrev", "codigo", "código", "sigla", "siglas")
            if k in idx
        ),
        None,
    )
    jefe_idx = next(
        (idx[k] for k in ("jefe", "jefe departamento", "responsable") if k in idx),
        None,
    )
    if dep_idx is None or abr_idx is None:
        return []

    rows: list[dict[str, str]] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        departamento = _cell_str(row[dep_idx] if dep_idx < len(row) else None)
        abreviatura = _cell_str(row[abr_idx] if abr_idx < len(row) else None)
        jefe = ""
        if jefe_idx is not None and jefe_idx < len(row):
            jefe = _cell_str(row[jefe_idx])
        if not departamento and not abreviatura:
            continue
        rows.append(
            {
                "departamento": departamento,
                "abreviatura": abreviatura,
                "jefe": jefe,
            }
        )
    return rows


def replace_departamentos(rows: list[dict[str, str]]) -> tuple[int, int]:
    """Sustituye el catálogo completo. Devuelve (insertadas, omitidas).

    Si la fila Excel no trae jefe, se conserva el jefe ya guardado (si existe).
    """
    ensure_departamentos_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT abreviatura, jefe FROM departamentos")
            prev_jefes = {
                str(r["abreviatura"]).strip().casefold(): (str(r["jefe"]).strip() if r.get("jefe") else "")
                for r in cur.fetchall()
                if r.get("abreviatura")
            }

    entries: dict[str, dict[str, str]] = {}
    skipped = 0
    for row in rows:
        abrev = (row.get("abreviatura") or "").strip()
        nombre = (row.get("departamento") or "").strip()
        jefe = (row.get("jefe") or "").strip()
        if not abrev or not nombre:
            skipped += 1
            continue
        if not jefe:
            jefe = prev_jefes.get(abrev.casefold(), "")
        entries[abrev.casefold()] = {
            "abreviatura": abrev,
            "departamento": nombre,
            "jefe": jefe,
        }

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM departamentos")
            for entry in entries.values():
                cur.execute(
                    """
                    INSERT INTO departamentos (
                        abreviatura, departamento, jefe, updated_at
                    )
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (
                        entry["abreviatura"],
                        entry["departamento"],
                        entry["jefe"] or None,
                    ),
                )
    return len(entries), skipped


def _is_religion_departamento(row: dict[str, Any]) -> bool:
    """Religión / enseñanza religiosa: van al final del listado."""
    nombre = normalize_for_sort(str(row.get("departamento") or ""))
    abrev = normalize_for_sort(str(row.get("abreviatura") or ""))
    return (
        nombre.startswith("religion")
        or "religiosa" in nombre
        or abrev.startswith("rel")
    )


def list_departamentos() -> list[dict[str, Any]]:
    ensure_departamentos_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT departamento, abreviatura, jefe, updated_at
                FROM departamentos
                WHERE departamento IS NOT NULL
                  AND BTRIM(departamento) <> ''
                """
            )
            rows = [dict(r) for r in cur.fetchall()]
    rows.sort(
        key=lambda r: (
            1 if _is_religion_departamento(r) else 0,
            normalize_for_sort(str(r.get("departamento") or "")),
        )
    )
    return rows


def get_departamento_match(ref: str | None) -> dict[str, Any] | None:
    """Localiza departamento por nombre o abreviatura (case-insensitive)."""
    key = (ref or "").strip()
    if not key:
        return None
    ensure_departamentos_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT departamento, abreviatura, jefe, updated_at
                FROM departamentos
                WHERE LOWER(BTRIM(departamento)) = LOWER(BTRIM(%s))
                   OR LOWER(BTRIM(abreviatura)) = LOWER(BTRIM(%s))
                LIMIT 1
                """,
                (key, key),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def user_ve_todas_materias_competencias(user: dict | None) -> bool:
    """Directivos ven todas las materias; el resto solo las de su departamento."""
    if not user:
        return False
    role = (user.get("role") or "").strip().lower()
    return role in ROLES_ADMINISTRATIVOS


def departamentos_equivalentes(a: str | None, b: str | None) -> bool:
    """True si ambas referencias apuntan al mismo departamento del catálogo."""
    ra = (a or "").strip()
    rb = (b or "").strip()
    if not ra or not rb:
        return False
    da = get_departamento_match(ra)
    db = get_departamento_match(rb)
    if da and db:
        abr_a = (da.get("abreviatura") or "").strip().casefold()
        abr_b = (db.get("abreviatura") or "").strip().casefold()
        if abr_a and abr_b:
            return abr_a == abr_b
    return ra.casefold() == rb.casefold()


def user_can_view_departamento_materias(
    user: dict | None, departamento_ref: str | None
) -> bool:
    """Consulta de materias: todas (directivo) o solo el departamento del usuario."""
    if user_ve_todas_materias_competencias(user):
        return True
    if not user:
        return False
    user_dep = (user.get("departamento") or "").strip()
    if not user_dep:
        return False
    return departamentos_equivalentes(user_dep, departamento_ref)


def user_can_edit_departamento_pd(user: dict | None, departamento_ref: str | None) -> bool:
    """Roles directivos siempre; jefe del departamento si la edición no está bloqueada."""
    if not user:
        return False
    role = (user.get("role") or "").strip().lower()
    if role in ROLES_ADMINISTRATIVOS:
        return True
    from db.competencias_pd_edicion import pd_jefes_bloqueados

    if pd_jefes_bloqueados():
        return False
    dep = get_departamento_match(departamento_ref)
    jefe = ((dep or {}).get("jefe") or "").strip()
    if not jefe:
        return False
    nombre = (user.get("name") or "").strip()
    if not nombre:
        return False
    return nombre.casefold() == jefe.casefold()


def list_miembros_departamento(
    *,
    departamento: str | None,
    abreviatura: str | None = None,
) -> list[dict[str, Any]]:
    """Usuarios del departamento (por nombre o abreviatura en users.departamento)."""
    keys = []
    for raw in (departamento, abreviatura):
        t = (raw or "").strip()
        if t and t.casefold() not in {k.casefold() for k in keys}:
            keys.append(t)
    if not keys:
        return []

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, alias, departamento
                FROM users
                WHERE active = 1
                  AND departamento IS NOT NULL
                  AND BTRIM(departamento) <> ''
                  AND LOWER(TRIM(departamento)) = ANY(%s)
                """,
                ([k.lower() for k in keys],),
            )
            rows = [dict(r) for r in cur.fetchall()]

    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows


def miembros_por_departamento(
    departamentos: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Mapa abreviatura → miembros, para la UI de jefes."""
    deps = departamentos if departamentos is not None else list_departamentos()
    out: dict[str, list[dict[str, Any]]] = {}
    for d in deps:
        abr = (d.get("abreviatura") or "").strip()
        if not abr:
            continue
        out[abr] = list_miembros_departamento(
            departamento=d.get("departamento"),
            abreviatura=abr,
        )
    return out


def update_departamento_jefe(abreviatura: str, jefe: str | None) -> bool:
    """Actualiza el jefe (nombre visible) del departamento. '' limpia la selección."""
    ensure_departamentos_schema()
    abr = (abreviatura or "").strip()
    if not abr:
        return False
    jefe_v = (jefe or "").strip() or None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE departamentos
                SET jefe = %s, updated_at = NOW()
                WHERE LOWER(BTRIM(abreviatura)) = LOWER(BTRIM(%s))
                """,
                (jefe_v, abr),
            )
            return cur.rowcount > 0


def get_departamentos_meta() -> dict[str, Any] | None:
    ensure_departamentos_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int AS row_count,
                       MAX(updated_at) AS updated_at
                FROM departamentos
                """
            )
            row = cur.fetchone()
    if not row or int(row["row_count"] or 0) == 0:
        return None
    return {
        "row_count": int(row["row_count"]),
        "updated_at": row.get("updated_at"),
    }
