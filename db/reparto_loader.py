"""Carga en batch de datos de Reparto (una conexión por departamento o control)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from db.connection import get_db
from db.reparto_carga_asignaciones import ensure_reparto_carga_asignaciones_schema
from db.reparto_carga_docente import (
    TABLE as CARGA_TABLE,
    _curso_key,
    _curso_label,
    _fmt as carga_fmt,
    _horas_por_grupo_efectivas,
    ensure_reparto_carga_docente_schema,
)
from db.reparto_horas_nominales import (
    TABLE as NOMINALES_TABLE,
    _dec as hn_dec,
    _fmt as hn_fmt,
    _totales as hn_totales,
    ensure_reparto_horas_nominales_schema,
)
from db.reparto_miembros import HORAS_JORNADA_COMPLETA, ensure_reparto_miembros_schema
from db.reparto_nominal_asignaciones import (
    TABLE as NOM_ASIG_TABLE,
    ensure_reparto_nominal_asignaciones_schema,
)
from db.reparto_otro_asignaciones import (
    TABLE as OTRO_ASIG_TABLE,
    ensure_reparto_otro_asignaciones_schema,
)
from db.reparto_otros import TABLE as OTROS_TABLE, ensure_reparto_otros_schema
from db.reparto_repartir_config import (
    MODO_RONDA_TODOS,
    MODOS_IDS,
    TABLE as CONFIG_TABLE,
    ensure_reparto_repartir_config_schema,
)
from utils.text import normalize_for_sort


def _depto_norm_sql(col: str) -> str:
    return f"LOWER(BTRIM({col})) = LOWER(BTRIM(%s))"


@dataclass
class RepartoDepartamentoSnapshot:
    nominales: list[dict]
    carga_items: list[dict]
    otros_items: list[dict]
    nominal_counts_user: dict[tuple[int, int], int]
    nominal_asignados_col: dict[int, int]
    carga_counts_user: dict[tuple[int, int], int]
    carga_asignados_col: dict[int, int]
    otro_counts_user: dict[tuple[int, int], int]
    otro_asignados_col: dict[int, int]
    miembros_config: dict[int, dict]
    repartir_cfg: dict
    profesores: list[dict]


def _otros_dec(value) -> Decimal | None:
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


def _otros_fmt(value) -> str:
    d = _otros_dec(value)
    if d is None:
        return ""
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f").rstrip("0").rstrip(".")


def _otros_totales(grupos: str, horas_por_grupo) -> Decimal | None:
    g = _otros_dec(grupos)
    h = _otros_dec(horas_por_grupo)
    if g is None or h is None:
        return None
    return g * h


_loader_schemas_ready = False


def _ensure_loader_schemas() -> None:
    global _loader_schemas_ready
    if _loader_schemas_ready:
        return
    ensure_reparto_horas_nominales_schema()
    ensure_reparto_carga_docente_schema()
    ensure_reparto_otros_schema()
    ensure_reparto_otro_asignaciones_schema()
    ensure_reparto_nominal_asignaciones_schema()
    ensure_reparto_carga_asignaciones_schema()
    ensure_reparto_miembros_schema()
    ensure_reparto_repartir_config_schema()
    _loader_schemas_ready = True


def load_departamento_snapshot(
    *,
    nombre: str,
    abreviatura: str,
) -> RepartoDepartamentoSnapshot:
    """Lee todos los datos de un departamento en una sola conexión."""
    _ensure_loader_schemas()

    key = (abreviatura or "").strip()
    nombre_n = (nombre or "").strip()
    abr_n = key

    nominales: list[dict] = []
    carga_items: list[dict] = []
    otros_items: list[dict] = []
    nominal_counts_user: dict[tuple[int, int], int] = {}
    nominal_asignados_col: dict[int, int] = {}
    carga_counts_user: dict[tuple[int, int], int] = {}
    carga_asignados_col: dict[int, int] = {}
    otro_counts_user: dict[tuple[int, int], int] = {}
    otro_asignados_col: dict[int, int] = {}
    miembros_config: dict[int, dict] = {}
    repartir_cfg = {"modo_eleccion": MODO_RONDA_TODOS, "turno_user_id": None}
    profesores: list[dict] = []

    if not key and not nombre_n:
        return RepartoDepartamentoSnapshot(
            nominales=nominales,
            carga_items=carga_items,
            otros_items=otros_items,
            nominal_counts_user=nominal_counts_user,
            nominal_asignados_col=nominal_asignados_col,
            carga_counts_user=carga_counts_user,
            carga_asignados_col=carga_asignados_col,
            otro_counts_user=otro_counts_user,
            otro_asignados_col=otro_asignados_col,
            miembros_config=miembros_config,
            repartir_cfg=repartir_cfg,
            profesores=profesores,
        )

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, concepto, grupos, horas_por_grupo, horas_totales
                FROM {NOMINALES_TABLE}
                WHERE {_depto_norm_sql("departamento_abrev")}
                ORDER BY id ASC
                """,
                (key,),
            )
            for r in cur.fetchall():
                nominales.append(
                    {
                        "id": int(r["id"]),
                        "concepto": str(r.get("concepto") or ""),
                        "grupos": str(r.get("grupos") or ""),
                        "horas_por_grupo": hn_fmt(r.get("horas_por_grupo")),
                        "horas_totales": hn_fmt(
                            r.get("horas_totales")
                            if r.get("horas_totales") is not None
                            else hn_totales(str(r.get("grupos") or ""), r.get("horas_por_grupo"))
                        ),
                    }
                )

            cur.execute(
                f"""
                SELECT id, etapa, curso_asignatura, materia_abrev, materia,
                       grupos, horas_por_grupo, horas_totales, tutoria, dc,
                       profesores_distintos
                FROM {CARGA_TABLE}
                WHERE {_depto_norm_sql("departamento_abrev")}
                ORDER BY id ASC
                """,
                (key,),
            )
            for r in cur.fetchall():
                try:
                    curso = int(r["curso_asignatura"]) if r.get("curso_asignatura") is not None else None
                except (TypeError, ValueError):
                    curso = None
                etapa = str(r.get("etapa") or "").strip() or None
                tutoria = bool(r.get("tutoria"))
                hpg_eff = _horas_por_grupo_efectivas(etapa, r.get("horas_por_grupo"), tutoria)
                ht = hn_totales(str(r.get("grupos") or ""), hpg_eff)
                carga_items.append(
                    {
                        "id": int(r["id"]),
                        "curso_label": _curso_label(etapa, curso),
                        "materia": str(r.get("materia") or r.get("materia_abrev") or ""),
                        "grupos": str(r.get("grupos") or ""),
                        "horas_por_grupo": carga_fmt(hpg_eff),
                        "horas_totales": carga_fmt(ht),
                        "tutoria": tutoria,
                        "dc": bool(r.get("dc")),
                        "curso_key": _curso_key(etapa, curso),
                        "materia_abrev": str(r.get("materia_abrev") or ""),
                        "profesores_distintos": int(
                            r.get("profesores_distintos") or 1
                        ),
                    }
                )

            cur.execute(
                f"""
                SELECT id, concepto, grupos, horas_por_grupo, horas_totales
                FROM {OTROS_TABLE}
                WHERE {_depto_norm_sql("departamento_abrev")}
                ORDER BY id ASC
                """,
                (key,),
            )
            for r in cur.fetchall():
                otros_items.append(
                    {
                        "id": int(r["id"]),
                        "concepto": str(r.get("concepto") or ""),
                        "grupos": str(r.get("grupos") or ""),
                        "horas_por_grupo": _otros_fmt(r.get("horas_por_grupo")),
                        "horas_totales": _otros_fmt(
                            r.get("horas_totales")
                            if r.get("horas_totales") is not None
                            else _otros_totales(str(r.get("grupos") or ""), r.get("horas_por_grupo"))
                        ),
                    }
                )

            cur.execute(
                f"""
                SELECT hora_nominal_id, user_id, COUNT(*) AS n
                FROM {NOM_ASIG_TABLE}
                WHERE {_depto_norm_sql("departamento_abrev")}
                GROUP BY hora_nominal_id, user_id
                """,
                (key,),
            )
            for r in cur.fetchall():
                nominal_counts_user[
                    (int(r["hora_nominal_id"]), int(r["user_id"]))
                ] = int(r["n"])

            cur.execute(
                f"""
                SELECT hora_nominal_id, COUNT(*) AS n
                FROM {NOM_ASIG_TABLE}
                WHERE {_depto_norm_sql("departamento_abrev")}
                GROUP BY hora_nominal_id
                """,
                (key,),
            )
            for r in cur.fetchall():
                nominal_asignados_col[int(r["hora_nominal_id"])] = int(r["n"])

            cur.execute(
                f"""
                SELECT otro_id, user_id, COUNT(*) AS n
                FROM {OTRO_ASIG_TABLE}
                WHERE {_depto_norm_sql("departamento_abrev")}
                GROUP BY otro_id, user_id
                """,
                (key,),
            )
            for r in cur.fetchall():
                otro_counts_user[
                    (int(r["otro_id"]), int(r["user_id"]))
                ] = int(r["n"])

            cur.execute(
                f"""
                SELECT otro_id, COUNT(*) AS n
                FROM {OTRO_ASIG_TABLE}
                WHERE {_depto_norm_sql("departamento_abrev")}
                GROUP BY otro_id
                """,
                (key,),
            )
            for r in cur.fetchall():
                otro_asignados_col[int(r["otro_id"])] = int(r["n"])

            cur.execute(
                f"""
                SELECT carga_id, user_id, COUNT(*) AS n
                FROM reparto_carga_asignaciones
                WHERE {_depto_norm_sql("departamento_abrev")}
                GROUP BY carga_id, user_id
                """,
                (key,),
            )
            for r in cur.fetchall():
                carga_counts_user[(int(r["carga_id"]), int(r["user_id"]))] = int(r["n"])

            cur.execute(
                f"""
                SELECT carga_id, COUNT(*) AS n
                FROM reparto_carga_asignaciones
                WHERE {_depto_norm_sql("departamento_abrev")}
                GROUP BY carga_id
                """,
                (key,),
            )
            for r in cur.fetchall():
                carga_asignados_col[int(r["carga_id"])] = int(r["n"])

            cur.execute(
                f"""
                SELECT user_id, horas, jornada_completa, no_tutor, tipo, orden, excluido
                FROM reparto_miembros
                WHERE {_depto_norm_sql("departamento_abrev")}
                """,
                (key,),
            )
            for row in cur.fetchall():
                miembros_config[int(row["user_id"])] = {
                    "horas": int(row["horas"]),
                    "jornada_completa": bool(row["jornada_completa"]),
                    "no_tutor": bool(row["no_tutor"]),
                    "tipo": (str(row.get("tipo") or "").strip() or None),
                    "orden": int(row["orden"]) if row.get("orden") is not None else None,
                    "excluido": bool(row.get("excluido")),
                }

            cur.execute(
                f"""
                SELECT modo_eleccion, turno_user_id
                FROM {CONFIG_TABLE}
                WHERE {_depto_norm_sql("departamento_abrev")}
                """,
                (key,),
            )
            row = cur.fetchone()
            if row:
                modo = str(row.get("modo_eleccion") or MODO_RONDA_TODOS).strip()
                if modo not in MODOS_IDS:
                    modo = MODO_RONDA_TODOS
                tid = row.get("turno_user_id")
                repartir_cfg = {
                    "modo_eleccion": modo,
                    "turno_user_id": int(tid) if tid is not None else None,
                }

            if nombre_n or abr_n:
                cur.execute(
                    """
                    SELECT id, name, email, role, alias, departamento
                    FROM users
                    WHERE active = 1
                      AND COALESCE(status, 'activo') = 'activo'
                      AND LOWER(TRIM(COALESCE(role, ''))) <> 'invitado'
                      AND (
                        LOWER(BTRIM(COALESCE(departamento, ''))) = LOWER(BTRIM(%s))
                        OR LOWER(BTRIM(COALESCE(departamento, ''))) = LOWER(BTRIM(%s))
                      )
                    """,
                    (nombre_n, abr_n),
                )
                profesores = [dict(r) for r in cur.fetchall()]

    profesores.sort(
        key=lambda r: normalize_for_sort(str(r.get("alias") or r.get("name") or ""))
    )
    return RepartoDepartamentoSnapshot(
        nominales=nominales,
        carga_items=carga_items,
        otros_items=otros_items,
        nominal_counts_user=nominal_counts_user,
        nominal_asignados_col=nominal_asignados_col,
        carga_counts_user=carga_counts_user,
        carga_asignados_col=carga_asignados_col,
        otro_counts_user=otro_counts_user,
        otro_asignados_col=otro_asignados_col,
        miembros_config=miembros_config,
        repartir_cfg=repartir_cfg,
        profesores=profesores,
    )


def load_control_horas_por_depto() -> dict[str, dict[str, Decimal]]:
    """
    Totales de horas por abreviatura de departamento en una conexión.
    Claves: h_nominales, h_carga, h_otros, h_miembros.
    """
    ensure_reparto_horas_nominales_schema()
    ensure_reparto_carga_docente_schema()
    ensure_reparto_otros_schema()
    ensure_reparto_otro_asignaciones_schema()
    ensure_reparto_miembros_schema()

    out: dict[str, dict[str, Decimal]] = {}

    def bucket(abr: str) -> dict[str, Decimal]:
        key = (abr or "").strip().lower()
        if key not in out:
            out[key] = {
                "h_nominales": Decimal(0),
                "h_carga": Decimal(0),
                "h_otros": Decimal(0),
                "h_miembros": Decimal(0),
            }
        return out[key]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT LOWER(BTRIM(departamento_abrev)) AS abr,
                       grupos, horas_por_grupo, horas_totales
                FROM {NOMINALES_TABLE}
                """
            )
            for r in cur.fetchall():
                abr = str(r["abr"])
                ht = hn_totales(
                    str(r.get("grupos") or ""), r.get("horas_por_grupo")
                )
                if ht is None:
                    ht = hn_dec(r.get("horas_totales")) or Decimal(0)
                b = bucket(abr)
                b["h_nominales"] += ht

            cur.execute(
                f"""
                SELECT LOWER(BTRIM(departamento_abrev)) AS abr,
                       etapa, grupos, horas_por_grupo, horas_totales, tutoria
                FROM {CARGA_TABLE}
                """
            )
            for r in cur.fetchall():
                abr = str(r["abr"])
                tutoria = bool(r.get("tutoria"))
                etapa = str(r.get("etapa") or "").strip() or None
                hpg_eff = _horas_por_grupo_efectivas(
                    etapa, r.get("horas_por_grupo"), tutoria
                )
                ht = hn_totales(str(r.get("grupos") or ""), hpg_eff)
                if ht is None:
                    ht = hn_dec(r.get("horas_totales")) or Decimal(0)
                b = bucket(abr)
                b["h_carga"] += ht

            cur.execute(
                f"""
                SELECT LOWER(BTRIM(departamento_abrev)) AS abr,
                       grupos, horas_por_grupo, horas_totales
                FROM {OTROS_TABLE}
                """
            )
            for r in cur.fetchall():
                abr = str(r["abr"])
                ht = hn_totales(
                    str(r.get("grupos") or ""), r.get("horas_por_grupo")
                )
                if ht is None:
                    ht = hn_dec(r.get("horas_totales")) or Decimal(0)
                b = bucket(abr)
                b["h_otros"] += ht

            cur.execute(
                """
                SELECT LOWER(BTRIM(d.abreviatura)) AS abr,
                       LOWER(BTRIM(d.departamento)) AS nom,
                       u.id AS user_id,
                       u.alias,
                       u.name,
                       rm.horas,
                       rm.jornada_completa,
                       rm.excluido
                FROM departamentos d
                JOIN users u ON (
                    LOWER(BTRIM(COALESCE(u.departamento, ''))) = LOWER(BTRIM(d.departamento))
                    OR LOWER(BTRIM(COALESCE(u.departamento, ''))) = LOWER(BTRIM(d.abreviatura))
                )
                LEFT JOIN reparto_miembros rm ON rm.user_id = u.id
                    AND LOWER(BTRIM(rm.departamento_abrev)) = LOWER(BTRIM(d.abreviatura))
                WHERE u.active = 1
                  AND COALESCE(u.status, 'activo') = 'activo'
                  AND LOWER(TRIM(COALESCE(u.role, ''))) <> 'invitado'
                """
            )
            seen: dict[str, set[int]] = {}
            for r in cur.fetchall():
                abr = str(r["abr"])
                uid = int(r["user_id"])
                if abr not in seen:
                    seen[abr] = set()
                if uid in seen[abr]:
                    continue
                seen[abr].add(uid)
                if bool(r.get("excluido")):
                    continue
                jornada = bool(r.get("jornada_completa")) if r.get("jornada_completa") is not None else True
                if jornada:
                    horas = Decimal(HORAS_JORNADA_COMPLETA)
                else:
                    horas = Decimal(int(r.get("horas") or HORAS_JORNADA_COMPLETA))
                b = bucket(abr)
                b["h_miembros"] += horas

    return out
