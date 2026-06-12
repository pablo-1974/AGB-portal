"""Avisos mostrados en la portada del portal (/portal).

Los tipos de aviso y los roles destinatarios se definirán aquí.
Cada aviso es un dict con al menos: id, title, body, kind, severity.
"""

from __future__ import annotations

from typing import Any

from db import funcionamiento_portal_feedback as fp_db
from db import listados_feedback as listados_db
from db import mantenimiento_feedback as mant_db
from db.moscosos_reservations import (
    dismiss_documentation_portal_notice,
    list_documentation_portal_notices_for_director,
)
from extraescolares.queries import list_unconfirmed_activities_for_portal_aviso
from incidencias.db import count_open_incidents
from utils.enums import ROLE_ADMIN, ROLE_DIRECTOR, ROLE_JEFE


def _aviso_incidencias_abiertas() -> dict[str, Any] | None:
    n = count_open_incidents()
    if n <= 0:
        return None
    return {
        "id": "incidencias_abiertas",
        "kind": "incidencias",
        "title": "Incidencias",
        "body": f"hay {n} incidencias sin cerrar",
    }


def _avisos_extraescolares_sin_confirmar(user: dict) -> list[dict[str, Any]]:
    acts = list_unconfirmed_activities_for_portal_aviso(int(user["id"]))
    avisos: list[dict[str, Any]] = []
    for act in acts:
        fecha_txt = act.get("fecha_display") or act.get("fecha_iso") or "—"
        avisos.append(
            {
                "id": f"extraescolares_sin_confirmar_{act['id']}",
                "kind": "extraescolares",
                "title": "Extraescolares",
                "body": f"todavía no has confirmado tu actividad del día {fecha_txt}",
                "href": f"/extraescolares/mis-actividades/{act['id']}#confirmar",
            }
        )
    return avisos


def _aviso_listados_buzon_sin_leer(user: dict) -> dict[str, Any] | None:
    if user.get("role") not in {ROLE_ADMIN, ROLE_JEFE}:
        return None
    n = listados_db.count_unread_feedback()
    if n <= 0:
        return None
    plural = "s" if n != 1 else ""
    return {
        "id": "listados_buzon_sin_leer",
        "kind": "buzones",
        "title": "Buzones",
        "body": f"hay {n} mensaje{plural} sin leer en el buzón de Listados",
        "href": "/buzones/listados/listar-mensajes",
    }


def _avisos_moscosos_documentacion_director(user: dict) -> list[dict[str, Any]]:
    if user.get("role") != ROLE_DIRECTOR:
        return []
    avisos: list[dict[str, Any]] = []
    for row in list_documentation_portal_notices_for_director(limit=20):
        res_id = int(row["id"])
        sender = (row.get("sender_label") or "Un profesor").strip()
        rd = row.get("reservation_date")
        if hasattr(rd, "strftime"):
            fecha_txt = rd.strftime("%d/%m/%Y")
        else:
            fecha_txt = str(rd)[:10] if rd else "—"
        user_id = int(row["user_id"])
        avisos.append(
            {
                "id": f"moscosos_documentacion_{res_id}",
                "kind": "moscosos",
                "title": "Moscosos",
                "body": (
                    f"{sender} ha enviado documentación de moscosos "
                    f"para el día {fecha_txt}"
                ),
                "href": f"/moscosos/cuadro-general?vista=profesores&profesor_id={user_id}",
                "dismiss_url": f"/portal/avisos/moscosos/documentacion/{res_id}/ok",
            }
        )
    return avisos


def _avisos_buzones_lectura_confirmada(user: dict) -> list[dict[str, Any]]:
    uid = int(user["id"])
    pending: list[tuple[Any, dict[str, Any]]] = []
    sources = (
        ("funcionamiento_portal", "Funcionamiento del portal", fp_db, "/buzones/funcionamiento-portal/mis-mensajes"),
        ("mantenimiento", "Mantenimiento", mant_db, "/buzones/mantenimiento/mis-mensajes"),
        ("listados", "Listados", listados_db, "/buzones/listados/mis-mensajes"),
    )
    for buzon_id, buzon_label, dbmod, href in sources:
        for row in dbmod.list_read_confirmations_for_author(user_id=uid, limit=20):
            reader = (row.get("reader_name") or "Un usuario").strip()
            aviso = {
                "id": f"buzon_lectura_{buzon_id}_{row['id']}",
                "kind": "buzones",
                "title": "Buzones",
                "body": (
                    f"{reader} ha confirmado la lectura de tu mensaje "
                    f"en el buzón de {buzon_label}"
                ),
                "href": href,
                "dismiss_url": f"/portal/avisos/buzones/{buzon_id}/{row['id']}/ok",
            }
            pending.append((row.get("read_at"), aviso))
    pending.sort(key=lambda item: item[0] or "", reverse=True)
    return [aviso for _, aviso in pending]


_BUZON_DISMISS_HANDLERS = {
    "funcionamiento_portal": fp_db.dismiss_read_notice_for_author,
    "mantenimiento": mant_db.dismiss_read_notice_for_author,
    "listados": listados_db.dismiss_read_notice_for_author,
}


def dismiss_buzon_read_aviso(*, buzon_id: str, feedback_id: int, user_id: int) -> bool:
    handler = _BUZON_DISMISS_HANDLERS.get(buzon_id)
    if handler is None:
        return False
    return handler(feedback_id=feedback_id, user_id=user_id)


def dismiss_moscosos_documentacion_aviso(*, reservation_id: int, user: dict) -> bool:
    if user.get("role") != ROLE_DIRECTOR:
        return False
    return dismiss_documentation_portal_notice(reservation_id=reservation_id)


def get_portal_avisos_for_user(user: dict | None) -> list[dict[str, Any]]:
    """Avisos visibles para el usuario en la portada del portal."""
    if not user:
        return []

    avisos: list[dict[str, Any]] = []
    role = user.get("role")

    if role in {ROLE_ADMIN, ROLE_JEFE}:
        inc = _aviso_incidencias_abiertas()
        if inc:
            avisos.append(inc)
        listados_buzon = _aviso_listados_buzon_sin_leer(user)
        if listados_buzon:
            avisos.append(listados_buzon)

    avisos.extend(_avisos_moscosos_documentacion_director(user))
    avisos.extend(_avisos_extraescolares_sin_confirmar(user))
    avisos.extend(_avisos_buzones_lectura_confirmada(user))

    return avisos
