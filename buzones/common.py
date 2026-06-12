"""Utilidades compartidas (solo formato; cada app tiene su BD y rutas)."""

from __future__ import annotations

from datetime import datetime


def format_sent_at(sent_at) -> tuple[str, str]:
    if sent_at is None:
        return "", ""
    if isinstance(sent_at, datetime):
        dt = sent_at
    else:
        try:
            dt = datetime.fromisoformat(str(sent_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return str(sent_at), ""
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")


def rows_for_list(
    rows: list[dict],
    *,
    tipo_labels: dict[str, str],
    include_user: bool = False,
) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        fecha, hora = format_sent_at(r.get("sent_at"))
        tipo = r.get("tipo") or ""
        read_at = r.get("read_at")
        item = {
            "id": r.get("id"),
            "fecha": fecha,
            "hora": hora,
            "tipo": tipo,
            "tipo_label": tipo_labels.get(tipo) or tipo,
            "mensaje": r.get("mensaje") or "",
            "is_read": read_at is not None,
        }
        if include_user:
            item["user_name"] = (r.get("user_name") or "").strip() or "—"
        out.append(item)
    return out
