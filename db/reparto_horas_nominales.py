"""Horas nominales por departamento (Reparto)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from db.connection import get_db

TABLE = "reparto_horas_nominales"
_schema_ready = False


def ensure_reparto_horas_nominales_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SERIAL PRIMARY KEY,
                    departamento_abrev TEXT NOT NULL,
                    concepto TEXT NOT NULL DEFAULT '',
                    grupos TEXT NOT NULL DEFAULT '',
                    horas_por_grupo NUMERIC(8, 2),
                    horas_totales NUMERIC(8, 2),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_hn_depto
                ON {TABLE} (departamento_abrev, id)
                """
            )
    _schema_ready = True


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    raw = str(value).strip().replace(",", ".")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _totales(grupos: str, horas_por_grupo) -> Decimal | None:
    g = _dec(grupos)
    h = _dec(horas_por_grupo)
    if g is None or h is None:
        return None
    return g * h


def _fmt(value) -> str:
    d = _dec(value)
    if d is None:
        return ""
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f").rstrip("0").rstrip(".")


def list_horas_nominales(departamento_abrev: str) -> list[dict]:
    ensure_reparto_horas_nominales_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, concepto, grupos, horas_por_grupo, horas_totales
                FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                ORDER BY id ASC
                """,
                (key,),
            )
            rows = []
            for r in cur.fetchall():
                rows.append(
                    {
                        "id": int(r["id"]),
                        "concepto": str(r.get("concepto") or ""),
                        "grupos": str(r.get("grupos") or ""),
                        "horas_por_grupo": _fmt(r.get("horas_por_grupo")),
                        "horas_totales": _fmt(
                            r.get("horas_totales")
                            if r.get("horas_totales") is not None
                            else _totales(str(r.get("grupos") or ""), r.get("horas_por_grupo"))
                        ),
                    }
                )
            return rows


def add_hora_nominal(
    *,
    departamento_abrev: str,
    concepto: str,
    grupos: str,
    horas_por_grupo: str,
) -> bool:
    """Inserta una fila. Devuelve False si no hay nada que guardar."""
    ensure_reparto_horas_nominales_schema()
    key = (departamento_abrev or "").strip()
    concepto_n = (concepto or "").strip()
    grupos_n = (grupos or "").strip()
    hpg = _dec(horas_por_grupo)
    ht = _totales(grupos_n, hpg)
    if not key:
        return False
    if not concepto_n and not grupos_n and hpg is None:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    departamento_abrev, concepto, grupos,
                    horas_por_grupo, horas_totales
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (key, concepto_n, grupos_n, hpg, ht),
            )
    return True


def update_hora_nominal(
    *,
    fila_id: int,
    departamento_abrev: str,
    concepto: str,
    grupos: str,
    horas_por_grupo: str,
) -> bool:
    ensure_reparto_horas_nominales_schema()
    key = (departamento_abrev or "").strip()
    if not key or int(fila_id) <= 0:
        return False
    concepto_n = (concepto or "").strip()
    grupos_n = (grupos or "").strip()
    hpg = _dec(horas_por_grupo)
    ht = _totales(grupos_n, hpg)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET concepto = %s,
                    grupos = %s,
                    horas_por_grupo = %s,
                    horas_totales = %s
                WHERE id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (concepto_n, grupos_n, hpg, ht, int(fila_id), key),
            )
            return cur.rowcount > 0


def delete_hora_nominal(*, fila_id: int, departamento_abrev: str) -> bool:
    ensure_reparto_horas_nominales_schema()
    key = (departamento_abrev or "").strip()
    if not key or int(fila_id) <= 0:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE}
                WHERE id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (int(fila_id), key),
            )
            return cur.rowcount > 0
