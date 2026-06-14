"""Respuestas HTTP para PDF generados en disco (evita fallos de FileResponse en Windows)."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from starlette.responses import Response


def safe_pdf_filename(stem: str, *, ext: str = "pdf") -> str:
    safe = re.sub(r"[^\w.\- ]+", "_", (stem or "").strip(), flags=re.UNICODE)
    safe = re.sub(r"\s+", "_", safe).strip("._") or "documento"
    return f"{safe[:72]}.{ext.lstrip('.')}"


def pdf_attachment_response(path: str | os.PathLike[str], *, filename: str) -> Response:
    """
    Lee el PDF del disco y responde con bytes.
    Starlette FileResponse hace stat async y en Windows el .pdf temporal
    a veces ya no existe → RuntimeError «File at path … does not exist».
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"No se generó el PDF: {p}")
    data = p.read_bytes()
    try:
        p.unlink()
    except OSError:
        pass
    if len(data) < 32:
        raise ValueError(f"El PDF generado está vacío ({len(data)} bytes)")
    fn = safe_pdf_filename(Path(filename).stem, ext=Path(filename).suffix.lstrip(".") or "pdf")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


def pdf_attachment_from_builder(
    build_fn: Callable[[str], None],
    *,
    filename: str,
) -> Response:
    """Crea un .pdf temporal, ejecuta build_fn(path) y devuelve la respuesta."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    path = tmp.name
    tmp.close()
    try:
        build_fn(path)
        return pdf_attachment_response(path, filename=filename)
    except Exception:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
        raise
