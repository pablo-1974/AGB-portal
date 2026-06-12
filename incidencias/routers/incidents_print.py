# routers/incidents_print.py

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from auth import load_user_dep
from db.incidents import get_incident_by_id
from db.users import get_user_by_id
from utils.enums import PERM_EDITAR_INCIDENCIA
from utils.pdf_incident_ticket import incident_ticket_pdf
from utils.permissions import has_permission

router = APIRouter()


def _nombre_para_firma_jefatura(teacher_name: str) -> str:
    """Si viene como «APELLIDOS, Nombre», mostrar «Nombre APELLIDOS» en la firma."""
    t = (teacher_name or "").strip()
    if ", " in t:
        apellidos, nombre = t.split(", ", 1)
        return f"{nombre.strip()} {apellidos.strip()}".strip()
    return t


def _firma_enviado_por(*, teacher_id: int, teacher_name: str) -> str:
    """Texto «Enviado por …» en el PDF: alias del usuario o nombre formateado."""
    u = get_user_by_id(teacher_id)
    if u:
        alias = str(u.get("alias") or "").strip()
        if alias:
            return alias
        name = str(u.get("name") or "").strip()
        if name:
            return _nombre_para_firma_jefatura(name)
    return _nombre_para_firma_jefatura(teacher_name)


def _enviado_dt_desde_incidente(inc: dict) -> datetime:
    """Fecha/hora en que el profesor registró el parte (created_at en BD)."""
    raw = inc.get("created_at") if inc else None
    if raw is None:
        return datetime.now()
    if isinstance(raw, datetime):
        return raw
    s = str(raw).strip()
    if not s:
        return datetime.now()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    return datetime.now()


@router.get("/incidents/print/{incident_id}")
def print_incident_ticket(
    incident_id: int,
    user: dict = Depends(load_user_dep),
):
    # Seguridad: solo quien puede editar puede imprimir
    if not has_permission(user, PERM_EDITAR_INCIDENCIA):
        raise HTTPException(status_code=403)

    inc = get_incident_by_id(incident_id)
    if not inc:
        raise HTTPException(status_code=404)

    pdf_bytes = incident_ticket_pdf(
        alumno=inc["alumno"],
        fecha=inc["fecha"],
        hora=inc["hora"],
        profesor=inc["teacher_name"],
        descripcion=inc["descripcion"],
        gravedad_inicial=inc["gravedad_inicial"],
        gravedad_final=inc.get("gravedad_final"),
        enviado_por=_firma_enviado_por(
            teacher_id=int(inc["teacher_id"]),
            teacher_name=str(inc.get("teacher_name") or ""),
        ),
        enviado_dt=_enviado_dt_desde_incidente(dict(inc)),
    )

    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=parte_incidencia_{incident_id}.pdf"
        },
    )
