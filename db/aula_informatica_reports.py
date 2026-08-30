"""Informes de sesión en aula de informática."""

from __future__ import annotations

import json
from datetime import date

from db.connection import get_db

TABLE_REPORTS = "aula_informatica_reports"
TABLE_PUESTOS = "aula_informatica_report_puestos"

_schema_ready = False


def ensure_aula_informatica_reports_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_REPORTS} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    aula_id TEXT NOT NULL,
                    session_date DATE NOT NULL,
                    class_hour TEXT NOT NULL,
                    grupos JSONB NOT NULL DEFAULT '[]'::jsonb,
                    otras_incidencias TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_PUESTOS} (
                    id SERIAL PRIMARY KEY,
                    report_id INTEGER NOT NULL
                        REFERENCES {TABLE_REPORTS}(id) ON DELETE CASCADE,
                    puesto INTEGER NOT NULL CHECK (puesto >= 1 AND puesto <= 24),
                    student_id INTEGER NOT NULL REFERENCES students(id),
                    estado TEXT NOT NULL CHECK (estado IN ('buen_estado', 'incidencias')),
                    incidencia_text TEXT,
                    UNIQUE (report_id, puesto)
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_ai_reports_created
                ON {TABLE_REPORTS} (created_at DESC)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_ai_reports_user
                ON {TABLE_REPORTS} (user_id, created_at DESC)
                """
            )
    _schema_ready = True


def insert_report(
    *,
    user_id: int,
    aula_id: str,
    session_date: date,
    class_hour: str,
    grupos: list[str],
    otras_incidencias: str | None,
    puestos: list[dict],
) -> int:
    ensure_aula_informatica_reports_schema()
    otras = (otras_incidencias or "").strip() or None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE_REPORTS} (
                    user_id, aula_id, session_date, class_hour, grupos, otras_incidencias
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                RETURNING id
                """,
                (
                    int(user_id),
                    (aula_id or "").strip(),
                    session_date,
                    (class_hour or "").strip(),
                    json.dumps(sorted({g.strip() for g in grupos if g and str(g).strip()})),
                    otras,
                ),
            )
            report_id = int(cur.fetchone()["id"])
            for row in puestos:
                cur.execute(
                    f"""
                    INSERT INTO {TABLE_PUESTOS} (
                        report_id, puesto, student_id, estado, incidencia_text
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        report_id,
                        int(row["puesto"]),
                        int(row["student_id"]),
                        str(row["estado"]),
                        (row.get("incidencia") or "").strip() or None,
                    ),
                )
    return report_id


def has_report_for_session(
    *,
    user_id: int,
    aula_id: str,
    session_date: date,
    class_hour: str,
) -> bool:
    """¿Existe informe en Aula de Informática para usuario, aula, fecha y hora?"""
    ensure_aula_informatica_reports_schema()
    aula_key = str(aula_id or "").strip().lower()
    hour = str(class_hour or "").strip()
    if not aula_key or not hour:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT 1
                FROM {TABLE_REPORTS}
                WHERE user_id = %s
                  AND aula_id = %s
                  AND session_date = %s
                  AND class_hour = %s
                LIMIT 1
                """,
                (int(user_id), aula_key, session_date, hour),
            )
            return cur.fetchone() is not None


def list_reports_for_user(user_id: int) -> list[dict]:
    ensure_aula_informatica_reports_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, aula_id, session_date, class_hour, grupos, created_at
                FROM {TABLE_REPORTS}
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC
                """,
                (int(user_id),),
            )
            rows = list(cur.fetchall())

    items: list[dict] = []
    for row in rows:
        grupos_raw = row.get("grupos")
        if isinstance(grupos_raw, list):
            grupos = [str(g).strip() for g in grupos_raw if str(g).strip()]
        else:
            try:
                parsed = json.loads(grupos_raw or "[]")
                grupos = [str(g).strip() for g in parsed if str(g).strip()]
            except (TypeError, ValueError, json.JSONDecodeError):
                grupos = []
        session_date = row["session_date"]
        items.append(
            {
                "id": int(row["id"]),
                "aula_id": str(row["aula_id"] or "").strip(),
                "session_date": session_date,
                "session_date_iso": session_date.isoformat() if session_date else "",
                "class_hour": str(row["class_hour"] or "").strip(),
                "grupos": grupos,
                "grupos_display": ", ".join(grupos) if grupos else "—",
                "created_at": row.get("created_at"),
            }
        )
    return items


def list_all_reports(aula_id: str | None = None) -> list[dict]:
    """Todos los informes (vista directivos), opcionalmente filtrados por aula."""
    ensure_aula_informatica_reports_schema()
    clauses: list[str] = []
    params: list = []
    if aula_id:
        clauses.append("r.aula_id = %s")
        params.append(str(aula_id).strip().lower())
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    r.id,
                    r.user_id,
                    r.aula_id,
                    r.session_date,
                    r.class_hour,
                    r.grupos,
                    r.otras_incidencias,
                    r.created_at,
                    u.name AS user_name
                FROM {TABLE_REPORTS} r
                JOIN users u ON u.id = r.user_id
                {where_sql}
                ORDER BY r.created_at DESC, r.id DESC
                """,
                params,
            )
            rows = list(cur.fetchall())

    items: list[dict] = []
    for row in rows:
        grupos_raw = row.get("grupos")
        if isinstance(grupos_raw, list):
            grupos = [str(g).strip() for g in grupos_raw if str(g).strip()]
        else:
            try:
                parsed = json.loads(grupos_raw or "[]")
                grupos = [str(g).strip() for g in parsed if str(g).strip()]
            except (TypeError, ValueError, json.JSONDecodeError):
                grupos = []
        session_date = row["session_date"]
        items.append(
            {
                "id": int(row["id"]),
                "user_id": int(row["user_id"]),
                "user_name": str(row.get("user_name") or "").strip() or "—",
                "aula_id": str(row["aula_id"] or "").strip(),
                "session_date": session_date,
                "session_date_iso": session_date.isoformat() if session_date else "",
                "class_hour": str(row["class_hour"] or "").strip(),
                "grupos": grupos,
                "grupos_display": ", ".join(grupos) if grupos else "—",
                "otras_incidencias": str(row.get("otras_incidencias") or "").strip(),
                "created_at": row.get("created_at"),
            }
        )
    return items


def list_puesto_incidencias_for_reports(report_ids: list[int]) -> dict[int, list[dict]]:
    """Incidencias por puesto agrupadas por informe."""
    if not report_ids:
        return {}
    ensure_aula_informatica_reports_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    p.report_id,
                    p.puesto,
                    p.incidencia_text,
                    s.alumno,
                    s.grupo
                FROM {TABLE_PUESTOS} p
                JOIN students s ON s.id = p.student_id
                WHERE p.report_id = ANY(%s)
                  AND p.estado = 'incidencias'
                  AND p.incidencia_text IS NOT NULL
                  AND TRIM(p.incidencia_text) <> ''
                ORDER BY p.report_id, p.puesto
                """,
                (list({int(rid) for rid in report_ids}),),
            )
            rows = list(cur.fetchall())

    by_report: dict[int, list[dict]] = {}
    for row in rows:
        rid = int(row["report_id"])
        alumno = str(row.get("alumno") or "").strip()
        grupo = str(row.get("grupo") or "").strip()
        who = f"{alumno} ({grupo})" if grupo else alumno
        text = str(row.get("incidencia_text") or "").strip()
        puesto_n = int(row["puesto"])
        by_report.setdefault(rid, []).append(
            {
                "label": f"Puesto {puesto_n}",
                "detail": f"{who}: {text}" if who else text,
            }
        )
    return by_report


def list_puesto_history(aula_id: str, puesto: int) -> list[dict]:
    """Historial de uso de un puesto en un aula (más reciente primero)."""
    ensure_aula_informatica_reports_schema()
    puesto_n = int(puesto)
    if puesto_n < 1 or puesto_n > 24:
        return []
    aula_key = str(aula_id or "").strip().lower()
    if not aula_key:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    r.session_date,
                    r.class_hour,
                    r.created_at,
                    u.name AS user_name,
                    s.alumno,
                    s.grupo,
                    p.estado,
                    p.incidencia_text
                FROM {TABLE_PUESTOS} p
                JOIN {TABLE_REPORTS} r ON r.id = p.report_id
                JOIN users u ON u.id = r.user_id
                JOIN students s ON s.id = p.student_id
                WHERE r.aula_id = %s AND p.puesto = %s
                ORDER BY r.created_at DESC, r.id DESC
                """,
                (aula_key, puesto_n),
            )
            rows = list(cur.fetchall())

    items: list[dict] = []
    for row in rows:
        alumno = str(row.get("alumno") or "").strip()
        grupo = str(row.get("grupo") or "").strip()
        estado = str(row.get("estado") or "").strip()
        incidencia = str(row.get("incidencia_text") or "").strip()
        session_date = row["session_date"]
        items.append(
            {
                "session_date": session_date,
                "session_date_iso": session_date.isoformat() if session_date else "",
                "class_hour": str(row["class_hour"] or "").strip(),
                "user_name": str(row.get("user_name") or "").strip() or "—",
                "alumno": alumno or "—",
                "grupo": grupo or "—",
                "estado": estado,
                "incidencia": incidencia,
                "created_at": row.get("created_at"),
            }
        )
    return items


def get_report_for_user(report_id: int, user_id: int) -> dict | None:
    ensure_aula_informatica_reports_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, user_id, aula_id, session_date, class_hour, grupos, otras_incidencias
                FROM {TABLE_REPORTS}
                WHERE id = %s AND user_id = %s
                """,
                (int(report_id), int(user_id)),
            )
            report = cur.fetchone()
            if not report:
                return None
            cur.execute(
                f"""
                SELECT p.puesto, p.student_id, p.estado, p.incidencia_text,
                       s.alumno, s.grupo
                FROM {TABLE_PUESTOS} p
                JOIN students s ON s.id = p.student_id
                WHERE p.report_id = %s
                ORDER BY p.puesto
                """,
                (int(report_id),),
            )
            puesto_rows = list(cur.fetchall())

    grupos_raw = report.get("grupos")
    if isinstance(grupos_raw, list):
        grupos = [str(g).strip() for g in grupos_raw if str(g).strip()]
    else:
        try:
            parsed = json.loads(grupos_raw or "[]")
            grupos = [str(g).strip() for g in parsed if str(g).strip()]
        except (TypeError, ValueError, json.JSONDecodeError):
            grupos = []

    session_date = report["session_date"]
    puestos: list[dict] = []
    student_ids: list[int] = []
    for row in puesto_rows:
        sid = int(row["student_id"])
        student_ids.append(sid)
        alumno = str(row.get("alumno") or "").strip()
        grupo = str(row.get("grupo") or "").strip()
        label = f"{alumno} ({grupo})" if grupo else alumno
        incidencia = str(row.get("incidencia_text") or "").strip()
        puestos.append(
            {
                "puesto": int(row["puesto"]),
                "student_id": sid,
                "estado": str(row["estado"] or "").strip(),
                "incidencia": incidencia,
                "alumno_label": label,
                "grupo": grupo,
            }
        )

    return {
        "id": int(report["id"]),
        "aula_id": str(report["aula_id"] or "").strip(),
        "session_date": session_date.isoformat() if session_date else "",
        "class_hour": str(report["class_hour"] or "").strip(),
        "grupos": grupos,
        "otras_incidencias": str(report.get("otras_incidencias") or "").strip(),
        "puestos": puestos,
        "student_ids": sorted(set(student_ids)),
    }


def update_report(
    *,
    report_id: int,
    user_id: int,
    grupos: list[str],
    otras_incidencias: str | None,
    puestos: list[dict],
) -> bool:
    ensure_aula_informatica_reports_schema()
    otras = (otras_incidencias or "").strip() or None
    grupos_json = json.dumps(sorted({g.strip() for g in grupos if g and str(g).strip()}))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id FROM {TABLE_REPORTS}
                WHERE id = %s AND user_id = %s
                """,
                (int(report_id), int(user_id)),
            )
            if not cur.fetchone():
                return False
            cur.execute(
                f"""
                UPDATE {TABLE_REPORTS}
                SET grupos = %s::jsonb,
                    otras_incidencias = %s
                WHERE id = %s AND user_id = %s
                """,
                (grupos_json, otras, int(report_id), int(user_id)),
            )
            cur.execute(
                f"DELETE FROM {TABLE_PUESTOS} WHERE report_id = %s",
                (int(report_id),),
            )
            for row in puestos:
                cur.execute(
                    f"""
                    INSERT INTO {TABLE_PUESTOS} (
                        report_id, puesto, student_id, estado, incidencia_text
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        int(report_id),
                        int(row["puesto"]),
                        int(row["student_id"]),
                        str(row["estado"]),
                        (row.get("incidencia") or "").strip() or None,
                    ),
                )
    return True
