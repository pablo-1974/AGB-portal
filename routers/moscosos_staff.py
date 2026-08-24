"""Acciones de equipo directivo en Moscosos (anular reserva de cualquier profesor)."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse

from db.action_logs import log_moscosos_action
from db.connection import get_db
from moscosos.deps import require_moscosos_staff

router = APIRouter(
    prefix="/moscosos",
    tags=["moscosos"],
    dependencies=[Depends(require_moscosos_staff)],
)

MoscososStaffUser = Annotated[dict, Depends(require_moscosos_staff)]


def _safe_cuadro_next(raw: str) -> str:
    path = (raw or "").strip()
    if path.startswith("/moscosos/cuadro-general"):
        return path.split("#", 1)[0]
    return "/moscosos/cuadro-general"


def _with_status(url: str, status: str) -> str:
    parsed = urlparse(url)
    pairs = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "status"
    ]
    pairs.append(("status", status))
    return urlunparse(parsed._replace(query=urlencode(pairs)))


def _staff_delete_reservation(reservation_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.user_id, r.reservation_date, r.trimester, r.slot,
                       r.documentation_sent_at,
                       u.name AS user_name
                FROM moscosos_reservations r
                JOIN users u ON u.id = r.user_id
                WHERE r.id = %s
                """,
                (reservation_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cur.execute(
                "DELETE FROM moscosos_reservations WHERE id = %s",
                (reservation_id,),
            )
            if cur.rowcount <= 0:
                return None
            return {
                "id": int(row["id"]),
                "user_id": int(row["user_id"]),
                "user_name": str(row.get("user_name") or "").strip(),
                "reservation_date": row["reservation_date"],
                "trimester": int(row["trimester"]),
                "slot": int(row["slot"]),
                "doc_sent": row.get("documentation_sent_at") is not None,
            }


@router.post("/cuadro-general/anular")
def moscosos_staff_anular(
    user: MoscososStaffUser,
    reservation_id: int = Form(...),
    next_url: str = Form(""),
):
    dest = _safe_cuadro_next(next_url)
    deleted = _staff_delete_reservation(int(reservation_id))
    if not deleted:
        return RedirectResponse(_with_status(dest, "cancel_error"), status_code=303)

    d = deleted["reservation_date"]
    date_iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
    who = deleted.get("user_name") or f"usuario #{deleted['user_id']}"
    detail = (
        f"Anulación staff moscoso: {date_iso} · reserva #{deleted['id']} "
        f"· {who} (#{deleted['user_id']})"
    )
    if deleted.get("doc_sent"):
        detail += " · tenía documentación enviada"
    log_moscosos_action(
        user_id=int(user["id"]),
        action="reservation_cancel_staff",
        entity_id=int(deleted["id"]),
        detail=detail,
    )
    return RedirectResponse(_with_status(dest, "cancelled"), status_code=303)
