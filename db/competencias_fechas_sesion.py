"""Fechas de las sesiones de evaluación (Configuración)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from db.connection import get_db
from utils.time_madrid import TZ_MADRID, now_madrid, today_madrid

TABLE = "competencias_fechas_sesion"
HORA_CIERRE = time(23, 55)
DIAS_AVISO_CALIFICACIONES = 2
SESION_ESO = ""
SESION_ORD = "ordinaria"
SESION_EXT = "extraordinaria"

_schema_ready = False


def ensure_competencias_fechas_sesion_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    grupo TEXT NOT NULL,
                    sesion TEXT NOT NULL DEFAULT '',
                    fecha DATE,
                    PRIMARY KEY (grupo, sesion)
                )
                """
            )
    _schema_ready = True


def _norm_grupo(grupo: str) -> str:
    return (grupo or "").strip()


def _norm_sesion(sesion: str | None) -> str:
    key = (sesion or "").strip().lower()
    if key in (SESION_ORD, SESION_EXT):
        return key
    return SESION_ESO


def clave_sesion_fecha(*, grupo: str, stage: str | None, sesion: str | None) -> str:
    """ESO: una sola fecha. Bach: ordinaria (por defecto) o extraordinaria."""
    if stage == "bachillerato":
        key = _norm_sesion(sesion)
        return key if key else SESION_ORD
    return SESION_ESO


def get_fecha_sesion(*, grupo: str, sesion: str) -> date | None:
    ensure_competencias_fechas_sesion_schema()
    g = _norm_grupo(grupo)
    s = _norm_sesion(sesion) if sesion else SESION_ESO
    if not g:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT fecha
                FROM {TABLE}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                  AND sesion = %s
                """,
                (g, s),
            )
            row = cur.fetchone()
    if not row or row.get("fecha") is None:
        return None
    fd = row["fecha"]
    return fd if isinstance(fd, date) else date.fromisoformat(str(fd)[:10])


def map_fechas_sesion() -> dict[tuple[str, str], date]:
    ensure_competencias_fechas_sesion_schema()
    out: dict[tuple[str, str], date] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT grupo, sesion, fecha FROM {TABLE}")
            for r in cur.fetchall():
                g = _norm_grupo(str(r.get("grupo") or ""))
                s = _norm_sesion(str(r.get("sesion") or ""))
                fd = r.get("fecha")
                if not g or fd is None:
                    continue
                if not isinstance(fd, date):
                    fd = date.fromisoformat(str(fd)[:10])
                out[(g, s)] = fd
                out[(g.casefold(), s)] = fd
    return out


def save_fechas_sesion(items: list[tuple[str, str, date | None]]) -> None:
    ensure_competencias_fechas_sesion_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            for grupo, sesion, fecha in items:
                g = _norm_grupo(grupo)
                s = _norm_sesion(sesion)
                if not g:
                    continue
                cur.execute(
                    f"""
                    INSERT INTO {TABLE} (grupo, sesion, fecha)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (grupo, sesion)
                    DO UPDATE SET fecha = EXCLUDED.fecha
                    """,
                    (g, s, fecha),
                )


def grupos_extra_antes_que_ordinaria(
    items: list[tuple[str, str, date | None]],
) -> list[str]:
    """Grupos de Bachillerato cuya extraordinaria es anterior a la ordinaria."""
    por_grupo: dict[str, dict[str, date | None]] = {}
    orden: list[str] = []
    for grupo, sesion, fecha in items:
        g = _norm_grupo(grupo)
        s = _norm_sesion(sesion)
        if not g or s not in (SESION_ORD, SESION_EXT):
            continue
        if g not in por_grupo:
            por_grupo[g] = {}
            orden.append(g)
        por_grupo[g][s] = fecha
    mal: list[str] = []
    for g in orden:
        pares = por_grupo[g]
        ord_d = pares.get(SESION_ORD)
        ext_d = pares.get(SESION_EXT)
        if ord_d and ext_d and ext_d < ord_d:
            mal.append(g)
    return mal


def format_fecha_sesion(value: date | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d/%m/%Y")


def datetime_cierre(fecha_sesion: date) -> datetime:
    """Último instante para introducir notas: día anterior a las 23:55 (Madrid)."""
    dia = fecha_sesion - timedelta(days=1)
    return datetime.combine(dia, HORA_CIERRE, tzinfo=TZ_MADRID)


def plazo_abierto(fecha_sesion: date | None, *, now: datetime | None = None) -> bool:
    """Sin fecha configurada el plazo queda abierto."""
    if fecha_sesion is None:
        return True
    moment = now or now_madrid()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=TZ_MADRID)
    else:
        moment = moment.astimezone(TZ_MADRID)
    return moment <= datetime_cierre(fecha_sesion)


def puede_introducir_calificaciones(
    fecha_sesion: date | None,
    *,
    es_directivo: bool,
    now: datetime | None = None,
) -> bool:
    """Roles directivos califican siempre; el resto hasta el cierre del plazo."""
    if es_directivo:
        return True
    return plazo_abierto(fecha_sesion, now=now)


def hoy_madrid() -> date:
    return today_madrid()


def en_ventana_aviso_calificaciones(
    fecha_sesion: date | None,
    *,
    today: date | None = None,
) -> bool:
    """Aviso al profesorado: 2 días antes y el día anterior a la sesión."""
    if fecha_sesion is None:
        return False
    dia = today or hoy_madrid()
    delta = (fecha_sesion - dia).days
    return 1 <= delta <= DIAS_AVISO_CALIFICACIONES


def info_plazo(
    *,
    grupo: str,
    stage: str | None,
    sesion: str | None,
    es_directivo: bool = False,
) -> dict[str, Any]:
    clave = clave_sesion_fecha(grupo=grupo, stage=stage, sesion=sesion)
    fecha = get_fecha_sesion(grupo=grupo, sesion=clave)
    calendario_abierto = plazo_abierto(fecha)
    cierre = datetime_cierre(fecha) if fecha else None
    return {
        "fecha_sesion": fecha,
        "fecha_sesion_display": format_fecha_sesion(fecha),
        "plazo_calendario_abierto": calendario_abierto,
        "plazo_abierto": puede_introducir_calificaciones(
            fecha, es_directivo=es_directivo
        ),
        "cierre_display": cierre.strftime("%d/%m/%Y %H:%M") if cierre else "",
        "sesion_fecha": clave,
    }
