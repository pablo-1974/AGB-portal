"""Matriz de pesos descriptor × criterio (Cálculos → Pesos)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from competencias.catalogo import (
    ETAPA_BACH,
    ETAPA_ESO,
    ETAPA_LABELS,
    ETAPAS_COMPETENCIAS,
    get_materia_por_clave,
    materias_con_flag_criterios,
)
from db.competencias_clave import list_descriptores_operativos
from db.competencias_materia_criterios import (
    list_criterios_materia,
    normalize_descriptor_code,
)
from db.competencias_materia_variables import COEF_CAMPOS, map_coef_materia

VARIABLES_PESO: tuple[tuple[str, str], ...] = (
    ("coef0", "coef0"),
    ("coef1", "coef1"),
    ("coef2", "coef2"),
)


def format_coef_es(value: Decimal | None) -> str:
    """Coeficiente en pantalla: hasta 4 decimales, coma decimal."""
    if value is None:
        return ""
    d = Decimal(str(value))
    if d == 0:
        return "0"
    text = format(d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")
    text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def list_materias_opciones_pesos() -> list[dict[str, Any]]:
    """Asignaturas con criterios (ESO y Bach) para el desplegable."""
    out: list[dict[str, Any]] = []
    for etapa in (ETAPA_ESO, ETAPA_BACH):
        for m in materias_con_flag_criterios(etapa):
            if not m.get("tiene_criterios"):
                continue
            nombre = (m.get("materia") or m.get("materia_key") or "").strip()
            curso = int(m["curso_asignatura"])
            out.append(
                {
                    "etapa": etapa,
                    "etapa_label": ETAPA_LABELS.get(etapa, etapa),
                    "curso": curso,
                    "key": m["materia_key"],
                    "materia": nombre,
                    "label": f"{ETAPA_LABELS.get(etapa, etapa)} · {curso}º · {nombre}",
                }
            )
    out.sort(key=lambda r: (r["etapa"], r["curso"], (r["materia"] or "").lower()))
    return out


def build_matriz_pesos(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    variable: str | None = None,
) -> dict[str, Any] | None:
    """Filas = descriptores operativos; columnas = criterios."""
    stage = (etapa or "").strip().lower()
    if stage not in ETAPAS_COMPETENCIAS:
        return None
    curso = int(curso_asignatura)
    key = (materia_key or "").strip()
    if not key:
        return None

    criterios = list_criterios_materia(
        etapa=stage,
        curso_asignatura=curso,
        materia_key=key,
    )
    crit_codes = [
        str(c.get("criterio") or "").strip()
        for c in criterios
        if str(c.get("criterio") or "").strip()
    ]
    if not crit_codes:
        return None

    materia = get_materia_por_clave(
        etapa=stage,
        curso_asignatura=curso,
        materia_key=key,
    )
    nombre = (materia or {}).get("materia") or (
        criterios[0].get("materia_nombre") if criterios else key
    )

    var = (variable or "").strip().lower() or None
    if var not in COEF_CAMPOS:
        var = None

    coef_map: dict[tuple[str, str], Decimal] = {}
    if var:
        coef_map = map_coef_materia(
            etapa=stage,
            curso_asignatura=curso,
            materia_key=key,
            campo=var,
        )

    descriptores = list_descriptores_operativos(stage)
    filas = []
    suma_label = {
        "coef0": "donumcru",
        "coef1": "Σ coef1",
        "coef2": "Σ coef2",
    }.get(var or "", "Σ")
    for desc in descriptores:
        desc_norm = normalize_descriptor_code(desc)
        pesos: dict[str, str] = {}
        total = Decimal("0")
        has_val = False
        for crit in crit_codes:
            if var:
                val = coef_map.get((desc_norm, crit))
                pesos[crit] = format_coef_es(val) if val is not None else ""
                if val is not None:
                    total += Decimal(str(val))
                    has_val = True
            else:
                pesos[crit] = ""
        filas.append(
            {
                "descriptor": desc,
                "pesos": pesos,
                "suma": format_coef_es(total) if has_val else "",
            }
        )

    return {
        "etapa": stage,
        "etapa_label": ETAPA_LABELS.get(stage, stage),
        "curso": curso,
        "materia_key": key,
        "materia": nombre,
        "criterios": crit_codes,
        "filas": filas,
        "variable": var,
        "suma_label": suma_label,
    }
