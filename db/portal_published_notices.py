"""Avisos publicados desde la app Publicar avisos (visibles en /portal)."""

from __future__ import annotations

from datetime import date
from html import escape
import re

from db.connection import get_db

TABLE = "portal_published_notices"
DISMISS_TABLE = "portal_published_notice_dismissals"
_schema_ready = False

TIPO_NUEVO_ALUMNO = "nuevo-alumno"
TIPO_BAJA_ALUMNO = "baja-alumno"
TIPO_SUSTITUCION = "sustitucion"
TIPO_REINCORPORACION = "reincorporacion"
TIPO_AVISO_LIBRE = "aviso-libre"
TIPO_PAA = "paa"
TIPO_EXPEDIENTE = "expediente-disciplinario"


def _log_notice_created(
    *,
    user_id: int | None,
    notice_id: int,
    action: str,
    detail: str | None = None,
) -> None:
    from db.action_logs import log_publicar_avisos_action

    log_publicar_avisos_action(
        user_id=int(user_id) if user_id is not None else None,
        action=action,
        entity_id=int(notice_id),
        detail=detail,
    )

ROLE_LABEL_AVISO_LIBRE = {
    "admin": "Administrador",
    "director": "Dirección",
    "jefe": "Jefatura de Estudios",
    "secretario": "Secretaría",
}


def ensure_portal_published_notices_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SERIAL PRIMARY KEY,
                    tipo TEXT NOT NULL,
                    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    alumno_nombre TEXT,
                    fecha_incorporacion DATE,
                    grupo TEXT,
                    optativas TEXT,
                    observaciones TEXT,
                    body_html TEXT NOT NULL
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_ppn_created_at
                ON {TABLE} (created_at DESC)
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {DISMISS_TABLE} (
                    notice_id INTEGER NOT NULL
                        REFERENCES {TABLE}(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    dismissed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (notice_id, user_id)
                )
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS sustituto_nombre TEXT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS sustituido_alias TEXT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS departamento TEXT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS autor_rol_label TEXT
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_ppnd_user_id
                ON {DISMISS_TABLE} (user_id)
                """
            )
    _schema_ready = True


def _format_date_es(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def format_optativas_html(raw: str) -> str:
    """Negrita en cada asignatura; comas y «y»/«e» quedan en texto normal."""
    s = (raw or "").strip()
    if not s:
        return ""
    tokens = re.split(r"(,\s*|\s+y\s+|\s+e\s+)", s, flags=re.IGNORECASE)
    parts: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        if re.fullmatch(r",\s*|\s+y\s+|\s+e\s+", tok, flags=re.IGNORECASE):
            parts.append(escape(tok))
        else:
            parts.append(f"<strong>{escape(tok.strip())}</strong>")
    return "".join(parts)


def build_nuevo_alumno_body_html(
    *,
    alumno_nombre: str,
    fecha: date,
    grupo: str,
    optativas: str,
    observaciones: str,
) -> str:
    nombre = escape((alumno_nombre or "").strip())
    grupo_esc = escape((grupo or "").strip())
    fecha_esc = escape(_format_date_es(fecha))
    parts = [
        "Se incorpora al centro el alumno ",
        f"<strong>{nombre}</strong>",
        " el día ",
        f"<strong>{fecha_esc}</strong>",
        " en el grupo ",
        f"<strong>{grupo_esc}</strong>",
        ".",
    ]
    opt_html = format_optativas_html(optativas)
    if opt_html:
        parts.append(" Como asignaturas optativas cursará: ")
        parts.append(opt_html)
        parts.append(".")
    obs = (observaciones or "").strip()
    if obs:
        parts.append(" ")
        parts.append(escape(obs))
    return "".join(parts)


def create_nuevo_alumno_notice(
    *,
    created_by: int,
    alumno_nombre: str,
    fecha_incorporacion: date,
    grupo: str,
    optativas: str,
    observaciones: str,
) -> int:
    ensure_portal_published_notices_schema()
    body_html = build_nuevo_alumno_body_html(
        alumno_nombre=alumno_nombre,
        fecha=fecha_incorporacion,
        grupo=grupo,
        optativas=optativas,
        observaciones=observaciones,
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    tipo, created_by, alumno_nombre, fecha_incorporacion,
                    grupo, optativas, observaciones, body_html
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    TIPO_NUEVO_ALUMNO,
                    int(created_by),
                    (alumno_nombre or "").strip(),
                    fecha_incorporacion,
                    (grupo or "").strip(),
                    (optativas or "").strip() or None,
                    (observaciones or "").strip() or None,
                    body_html,
                ),
            )
            nid = int(cur.fetchone()["id"])
    _log_notice_created(
        user_id=created_by,
        notice_id=nid,
        action="notice_nuevo_alumno",
        detail=(
            f"{(alumno_nombre or '').strip()} · {(grupo or '').strip()} · "
            f"{fecha_incorporacion.isoformat()}"
        ),
    )
    return nid


def list_undismissed_notices_for_user(*, user_id: int, limit: int = 50) -> list[dict]:
    ensure_portal_published_notices_schema()
    safe_limit = max(1, min(int(limit), 100))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT n.id, n.tipo, n.body_html, n.created_at, n.autor_rol_label
                FROM {TABLE} n
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM {DISMISS_TABLE} d
                    WHERE d.notice_id = n.id
                      AND d.user_id = %s
                )
                ORDER BY n.created_at DESC, n.id DESC
                LIMIT %s
                """,
                (int(user_id), safe_limit),
            )
            return list(cur.fetchall())


def build_baja_alumno_body_html(
    *,
    alumno_nombre: str,
    fecha: date,
    grupo: str,
) -> str:
    nombre = escape((alumno_nombre or "").strip())
    grupo_esc = escape((grupo or "").strip())
    fecha_esc = escape(_format_date_es(fecha))
    return (
        "El día "
        f"<strong>{fecha_esc}</strong> "
        "el alumno "
        f"<strong>{nombre}</strong> "
        "del grupo "
        f"<strong>{grupo_esc}</strong> "
        "se ha dado de baja en el centro."
    )


def create_baja_alumno_notice(
    *,
    created_by: int,
    alumno_nombre: str,
    fecha_baja: date,
    grupo: str,
) -> int:
    """Guarda la baja; la fecha se almacena en ``fecha_incorporacion`` (fecha del aviso)."""
    ensure_portal_published_notices_schema()
    body_html = build_baja_alumno_body_html(
        alumno_nombre=alumno_nombre,
        fecha=fecha_baja,
        grupo=grupo,
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    tipo, created_by, alumno_nombre, fecha_incorporacion,
                    grupo, body_html
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    TIPO_BAJA_ALUMNO,
                    int(created_by),
                    (alumno_nombre or "").strip(),
                    fecha_baja,
                    (grupo or "").strip(),
                    body_html,
                ),
            )
            nid = int(cur.fetchone()["id"])
    _log_notice_created(
        user_id=created_by,
        notice_id=nid,
        action="notice_baja_alumno",
        detail=(
            f"{(alumno_nombre or '').strip()} · {(grupo or '').strip()} · "
            f"{fecha_baja.isoformat()}"
        ),
    )
    return nid


def list_nuevo_alumno_notices(*, limit: int = 500) -> list[dict]:
    """Registros de avisos tipo «Nuevo alumno» para el listado (más recientes primero)."""
    return _list_alumno_notices_by_tipo(TIPO_NUEVO_ALUMNO, limit=limit)


def list_baja_alumno_notices(*, limit: int = 500) -> list[dict]:
    """Registros de avisos tipo «Baja de un alumno»."""
    return _list_alumno_notices_by_tipo(TIPO_BAJA_ALUMNO, limit=limit)


def build_sustitucion_body_html(
    *,
    fecha: date,
    sustituto_nombre: str,
    departamento: str,
    sustituido_alias: str,
) -> str:
    fecha_esc = escape(_format_date_es(fecha))
    nombre = escape((sustituto_nombre or "").strip())
    dept = escape((departamento or "").strip() or "—")
    alias = escape((sustituido_alias or "").strip())
    return (
        "El día "
        f"<strong>{fecha_esc}</strong> "
        "se incorpora el profesor "
        f"<strong>{nombre}</strong> "
        f"al departamento {dept} "
        "para cubrir la jornada de "
        f"<strong>{alias}</strong>."
    )


def create_sustitucion_notice(
    *,
    created_by: int | None,
    fecha: date,
    sustituto_nombre: str,
    departamento: str,
    sustituido_alias: str,
) -> int:
    ensure_portal_published_notices_schema()
    body_html = build_sustitucion_body_html(
        fecha=fecha,
        sustituto_nombre=sustituto_nombre,
        departamento=departamento,
        sustituido_alias=sustituido_alias,
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    tipo, created_by, fecha_incorporacion,
                    sustituto_nombre, sustituido_alias, departamento, body_html
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    TIPO_SUSTITUCION,
                    int(created_by) if created_by is not None else None,
                    fecha,
                    (sustituto_nombre or "").strip(),
                    (sustituido_alias or "").strip(),
                    (departamento or "").strip() or None,
                    body_html,
                ),
            )
            nid = int(cur.fetchone()["id"])
    _log_notice_created(
        user_id=created_by,
        notice_id=nid,
        action="notice_sustitucion",
        detail=(
            f"{(sustituto_nombre or '').strip()} cubre {(sustituido_alias or '').strip()} · "
            f"{fecha.isoformat()}"
        ),
    )
    return nid


def list_sustitucion_notices(*, limit: int = 500) -> list[dict]:
    return _list_sustitucion_like_notices(TIPO_SUSTITUCION, limit=limit)


def build_reincorporacion_body_html(
    *,
    fecha: date,
    profesor_alias: str,
    departamento: str,
) -> str:
    fecha_esc = escape(_format_date_es(fecha))
    alias = escape((profesor_alias or "").strip())
    dept = escape((departamento or "").strip() or "—")
    return (
        "El día "
        f"<strong>{fecha_esc}</strong> "
        "se reincorpora al centro el profesor "
        f"<strong>{alias}</strong> "
        "del departamento "
        f"<strong>{dept}</strong>."
    )


def create_reincorporacion_notice(
    *,
    created_by: int | None,
    fecha: date,
    profesor_alias: str,
    departamento: str,
    sustituto_nombre: str = "",
) -> int:
    """Aviso de reincorporación; ``sustituido_alias`` = reincorporado, ``sustituto_nombre`` = quien cubría."""
    ensure_portal_published_notices_schema()
    body_html = build_reincorporacion_body_html(
        fecha=fecha,
        profesor_alias=profesor_alias,
        departamento=departamento,
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    tipo, created_by, fecha_incorporacion,
                    sustituto_nombre, sustituido_alias, departamento, body_html
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    TIPO_REINCORPORACION,
                    int(created_by) if created_by is not None else None,
                    fecha,
                    (sustituto_nombre or "").strip() or None,
                    (profesor_alias or "").strip(),
                    (departamento or "").strip() or None,
                    body_html,
                ),
            )
            nid = int(cur.fetchone()["id"])
    _log_notice_created(
        user_id=created_by,
        notice_id=nid,
        action="notice_reincorporacion",
        detail=f"{(profesor_alias or '').strip()} · {fecha.isoformat()}",
    )
    return nid


def list_reincorporacion_notices(*, limit: int = 500) -> list[dict]:
    return _list_sustitucion_like_notices(TIPO_REINCORPORACION, limit=limit)


def create_aviso_libre_notice(
    *,
    created_by: int | None,
    role: str,
    mensaje: str,
) -> int:
    ensure_portal_published_notices_schema()
    texto = (mensaje or "").strip()
    if not texto:
        raise ValueError("El mensaje no puede estar vacío")
    rol_key = (role or "").strip().lower()
    rol_label = ROLE_LABEL_AVISO_LIBRE.get(rol_key)
    if not rol_label:
        raise ValueError("Rol no válido para aviso libre")
    # Conservar saltos de línea en el portal
    body_html = "<br>".join(escape(line) for line in texto.splitlines()) or escape(texto)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    tipo, created_by, fecha_incorporacion,
                    autor_rol_label, observaciones, body_html
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    TIPO_AVISO_LIBRE,
                    int(created_by) if created_by is not None else None,
                    date.today(),
                    rol_label,
                    texto,
                    body_html,
                ),
            )
            nid = int(cur.fetchone()["id"])
    preview = texto.replace("\n", " ").strip()
    if len(preview) > 80:
        preview = preview[:77] + "..."
    _log_notice_created(
        user_id=created_by,
        notice_id=nid,
        action="notice_aviso_libre",
        detail=preview,
    )
    return nid


def create_espacio_disponible_notice(
    *,
    created_by: int | None,
    app_nombre: str,
) -> int:
    """Aviso al pasar un espacio de «en obras» a «visible»."""
    ensure_portal_published_notices_schema()
    nombre = (app_nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre de la app no puede estar vacío")
    safe = escape(nombre)
    texto = f"{nombre}: la App {nombre} ya está disponible para los usuarios"
    body_html = (
        f"<strong>{safe}</strong>: la App {safe} ya está disponible para los usuarios"
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    tipo, created_by, fecha_incorporacion,
                    autor_rol_label, observaciones, body_html
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    TIPO_AVISO_LIBRE,
                    int(created_by) if created_by is not None else None,
                    date.today(),
                    None,  # sin etiqueta «Administrador» delante del texto
                    texto,
                    body_html,
                ),
            )
            nid = int(cur.fetchone()["id"])
    _log_notice_created(
        user_id=created_by,
        notice_id=nid,
        action="notice_espacio_disponible",
        detail=nombre,
    )
    return nid


def list_aviso_libre_notices(*, limit: int = 500) -> list[dict]:
    ensure_portal_published_notices_schema()
    safe_limit = max(1, min(int(limit), 2000))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    fecha_incorporacion,
                    created_at,
                    autor_rol_label,
                    observaciones
                FROM {TABLE}
                WHERE tipo = %s
                ORDER BY COALESCE(fecha_incorporacion, created_at::date) DESC,
                         id DESC
                LIMIT %s
                """,
                (TIPO_AVISO_LIBRE, safe_limit),
            )
            rows = list(cur.fetchall())

    out: list[dict] = []
    for row in rows:
        fd = row.get("fecha_incorporacion") or row.get("created_at")
        if hasattr(fd, "strftime"):
            # created_at is datetime
            if hasattr(fd, "date") and not isinstance(fd, date):
                fecha_display = fd.date().strftime("%d/%m/%Y")
            else:
                fecha_display = fd.strftime("%d/%m/%Y")
        else:
            fecha_display = str(fd)[:10] if fd else "—"
        out.append(
            {
                "id": int(row["id"]),
                "fecha_display": fecha_display,
                "autor": (row.get("autor_rol_label") or "").strip() or "—",
                "texto": (row.get("observaciones") or "").strip(),
            }
        )
    return out


def _list_sustitucion_like_notices(tipo: str, *, limit: int = 500) -> list[dict]:
    ensure_portal_published_notices_schema()
    safe_limit = max(1, min(int(limit), 2000))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    fecha_incorporacion,
                    sustituto_nombre,
                    sustituido_alias,
                    departamento,
                    created_at
                FROM {TABLE}
                WHERE tipo = %s
                ORDER BY fecha_incorporacion DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (tipo, safe_limit),
            )
            rows = list(cur.fetchall())

    out: list[dict] = []
    for row in rows:
        fd = row.get("fecha_incorporacion")
        if hasattr(fd, "strftime"):
            fecha_display = fd.strftime("%d/%m/%Y")
            fecha_iso = fd.isoformat()
        else:
            fecha_display = str(fd)[:10] if fd else "—"
            fecha_iso = str(fd)[:10] if fd else ""
        out.append(
            {
                "id": int(row["id"]),
                "fecha_display": fecha_display,
                "fecha_iso": fecha_iso,
                "sustituto_nombre": (row.get("sustituto_nombre") or "").strip(),
                "sustituido_alias": (row.get("sustituido_alias") or "").strip(),
                "departamento": (row.get("departamento") or "").strip(),
                "created_at": row.get("created_at"),
            }
        )
    return out


def _list_alumno_notices_by_tipo(tipo: str, *, limit: int = 500) -> list[dict]:
    ensure_portal_published_notices_schema()
    safe_limit = max(1, min(int(limit), 2000))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    alumno_nombre,
                    fecha_incorporacion,
                    grupo,
                    optativas,
                    observaciones,
                    created_at
                FROM {TABLE}
                WHERE tipo = %s
                ORDER BY fecha_incorporacion DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (tipo, safe_limit),
            )
            rows = list(cur.fetchall())

    out: list[dict] = []
    for row in rows:
        fd = row.get("fecha_incorporacion")
        if hasattr(fd, "strftime"):
            fecha_display = fd.strftime("%d/%m/%Y")
            fecha_iso = fd.isoformat()
        else:
            fecha_display = str(fd)[:10] if fd else "—"
            fecha_iso = str(fd)[:10] if fd else ""
        out.append(
            {
                "id": int(row["id"]),
                "alumno_nombre": (row.get("alumno_nombre") or "").strip(),
                "fecha_incorporacion": fd,
                "fecha_display": fecha_display,
                "fecha_iso": fecha_iso,
                "grupo": (row.get("grupo") or "").strip(),
                "optativas": (row.get("optativas") or "").strip(),
                "observaciones": (row.get("observaciones") or "").strip(),
                "created_at": row.get("created_at"),
            }
        )
    return out


def build_paa_body_html(
    *,
    alumno_nombre: str,
    grupo: str,
    fecha_inicio: date,
    fecha_final: date,
) -> str:
    nombre = escape((alumno_nombre or "").strip())
    grupo_esc = escape((grupo or "").strip())
    ini = escape(_format_date_es(fecha_inicio))
    fin = escape(_format_date_es(fecha_final))
    return (
        "La familia del alumno "
        f"<strong>{nombre}</strong> "
        "del grupo "
        f"<strong>{grupo_esc}</strong> "
        "ha firmado un Procedimiento de Acuerdo Abreviado por el que acepta "
        "la medida de suspensión del derecho de asistencia a todas las clases "
        "entre los días "
        f"<strong>{ini}</strong> "
        "y "
        f"<strong>{fin}</strong>, "
        "ambos incluidos. Esto no impide que pueda realizar los exámenes que "
        "tenga en esas fechas. Os pedimos que o bien a través del Teams del "
        "alumno o a través de Jefatura dejéis los trabajos de cada materia "
        "para que los realice en ese período."
    )


def create_paa_notice(
    *,
    created_by: int | None,
    alumno_nombre: str,
    grupo: str,
    fecha_inicio: date,
    fecha_final: date,
) -> int:
    ensure_portal_published_notices_schema()
    body_html = build_paa_body_html(
        alumno_nombre=alumno_nombre,
        grupo=grupo,
        fecha_inicio=fecha_inicio,
        fecha_final=fecha_final,
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    tipo, created_by, alumno_nombre, fecha_incorporacion,
                    grupo, body_html
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    TIPO_PAA,
                    int(created_by) if created_by is not None else None,
                    (alumno_nombre or "").strip(),
                    fecha_inicio,
                    (grupo or "").strip(),
                    body_html,
                ),
            )
            nid = int(cur.fetchone()["id"])
    _log_notice_created(
        user_id=created_by,
        notice_id=nid,
        action="notice_paa",
        detail=(
            f"{(alumno_nombre or '').strip()} · {(grupo or '').strip()} · "
            f"{fecha_inicio.isoformat()}–{fecha_final.isoformat()}"
        ),
    )
    return nid


def build_expediente_inicio_body_html(
    *,
    alumno_nombre: str,
    grupo: str,
    fecha_inicio: date,
    cautelar_inicio: date | None = None,
    cautelar_final: date | None = None,
    dias_cautelar: int | None = None,
) -> str:
    nombre = escape((alumno_nombre or "").strip())
    grupo_esc = escape((grupo or "").strip())
    fecha_esc = escape(_format_date_es(fecha_inicio))
    parts = [
        "El día ",
        f"<strong>{fecha_esc}</strong> ",
        "se ha iniciado un expediente disciplinario al alumno ",
        f"<strong>{nombre}</strong> ",
        "del grupo ",
        f"<strong>{grupo_esc}</strong>.",
    ]
    if (
        cautelar_inicio is not None
        and cautelar_final is not None
        and dias_cautelar is not None
        and int(dias_cautelar) > 0
    ):
        dias_n = int(dias_cautelar)
        dias_esc = escape(str(dias_n))
        palabra_dias = "día" if dias_n == 1 else "días"
        ci = escape(_format_date_es(cautelar_inicio))
        cf = escape(_format_date_es(cautelar_final))
        parts.extend(
            [
                " Cumplirá ",
                f"<strong>{dias_esc}</strong> ",
                f"{palabra_dias} de sanción cautelar, del ",
                f"<strong>{ci}</strong> ",
                "al ",
                f"<strong>{cf}</strong>.",
            ]
        )
    return "".join(parts)


def create_expediente_inicio_notice(
    *,
    created_by: int | None,
    alumno_nombre: str,
    grupo: str,
    fecha_inicio: date,
    cautelar_inicio: date | None = None,
    cautelar_final: date | None = None,
    dias_cautelar: int | None = None,
) -> int:
    ensure_portal_published_notices_schema()
    body_html = build_expediente_inicio_body_html(
        alumno_nombre=alumno_nombre,
        grupo=grupo,
        fecha_inicio=fecha_inicio,
        cautelar_inicio=cautelar_inicio,
        cautelar_final=cautelar_final,
        dias_cautelar=dias_cautelar,
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    tipo, created_by, alumno_nombre, fecha_incorporacion,
                    grupo, body_html
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    TIPO_EXPEDIENTE,
                    int(created_by) if created_by is not None else None,
                    (alumno_nombre or "").strip(),
                    fecha_inicio,
                    (grupo or "").strip(),
                    body_html,
                ),
            )
            nid = int(cur.fetchone()["id"])
    _log_notice_created(
        user_id=created_by,
        notice_id=nid,
        action="notice_expediente_inicio",
        detail=(
            f"{(alumno_nombre or '').strip()} · {(grupo or '').strip()} · "
            f"{fecha_inicio.isoformat()}"
        ),
    )
    return nid


def build_expediente_cierre_body_html(
    *,
    alumno_nombre: str,
    grupo: str,
    fecha_cierre: date,
    sancion_inicio: date,
    sancion_final: date,
    dias_sancion: int,
    dias_totales: int,
    tiene_cautelar: bool,
) -> str:
    nombre = escape((alumno_nombre or "").strip())
    grupo_esc = escape((grupo or "").strip())
    fecha_esc = escape(_format_date_es(fecha_cierre))
    si = escape(_format_date_es(sancion_inicio))
    sf = escape(_format_date_es(sancion_final))
    dias_s = int(dias_sancion)
    dias_t = int(dias_totales)
    palabra_s = "día" if dias_s == 1 else "días"
    palabra_t = "día" if dias_t == 1 else "días"
    parts = [
        "El día ",
        f"<strong>{fecha_esc}</strong> ",
        "se ha cerrado el expediente disciplinario del alumno ",
        f"<strong>{nombre}</strong> ",
        "del grupo ",
        f"<strong>{grupo_esc}</strong>. ",
        "Se impone una sanción de ",
        f"<strong>{escape(str(dias_s))}</strong> ",
        f"{palabra_s} lectivos, del ",
        f"<strong>{si}</strong> ",
        "al ",
        f"<strong>{sf}</strong>",
    ]
    if tiene_cautelar and dias_t > dias_s:
        parts.extend(
            [
                " (en total ",
                f"<strong>{escape(str(dias_t))}</strong> ",
                f"{palabra_t} lectivos incluyendo la sanción cautelar)",
            ]
        )
    parts.append(".")
    return "".join(parts)


def create_expediente_cierre_notice(
    *,
    created_by: int | None,
    alumno_nombre: str,
    grupo: str,
    fecha_cierre: date,
    sancion_inicio: date,
    sancion_final: date,
    dias_sancion: int,
    dias_totales: int,
    tiene_cautelar: bool,
) -> int:
    ensure_portal_published_notices_schema()
    body_html = build_expediente_cierre_body_html(
        alumno_nombre=alumno_nombre,
        grupo=grupo,
        fecha_cierre=fecha_cierre,
        sancion_inicio=sancion_inicio,
        sancion_final=sancion_final,
        dias_sancion=dias_sancion,
        dias_totales=dias_totales,
        tiene_cautelar=tiene_cautelar,
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    tipo, created_by, alumno_nombre, fecha_incorporacion,
                    grupo, body_html
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    TIPO_EXPEDIENTE,
                    int(created_by) if created_by is not None else None,
                    (alumno_nombre or "").strip(),
                    fecha_cierre,
                    (grupo or "").strip(),
                    body_html,
                ),
            )
            nid = int(cur.fetchone()["id"])
    _log_notice_created(
        user_id=created_by,
        notice_id=nid,
        action="notice_expediente_cierre",
        detail=(
            f"{(alumno_nombre or '').strip()} · {(grupo or '').strip()} · "
            f"{fecha_cierre.isoformat()}"
        ),
    )
    return nid


def dismiss_notice_for_user(*, notice_id: int, user_id: int) -> bool:
    ensure_portal_published_notices_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT 1 AS ok FROM {TABLE} WHERE id = %s",
                (int(notice_id),),
            )
            if not cur.fetchone():
                return False
            cur.execute(
                f"""
                INSERT INTO {DISMISS_TABLE} (notice_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT (notice_id, user_id) DO NOTHING
                """,
                (int(notice_id), int(user_id)),
            )
            return True
