"""Datos del informe de resultados por curso (ámbito Curso)."""

from __future__ import annotations

import math
from typing import Any

from competencias.evaluar_grupos import (
    _es_suspensa,
    _parse_nota_es,
    datos_sesion_evaluacion_grupo,
    grupos_para_evaluar,
)
from db.groups import get_group_curso, list_groups_with_course
from db.school_calendar import get_latest_calendar
from utils.group_stage import extract_course_num, stage_of
from utils.text import normalize_for_sort


def _bucket_cualitativo(texto: object) -> str | None:
    """Clasifica nota_acta en sb|nt|bi|su|sus; None si vacía / no interpretable."""
    from db.competencias_evaluacion import codigo_nota_acta_eso

    t = str(texto or "").strip()
    if not t or t == "—":
        return None
    up = t.upper().replace("Í", "I")
    if up in {"SB", "NT", "BI", "SU", "IN"}:
        return "sus" if up == "IN" else up.lower()
    # Bach numérico u otras formas → códigos ESO equivalentes.
    code = codigo_nota_acta_eso(t)
    if not code:
        return None
    return "sus" if code == "IN" else code.lower()


def build_informe_grupo_materias(
    grupo: str, *, datos: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Distribución de nota_acta por materia (curso actual) en un grupo."""
    nombre = (grupo or "").strip()
    if not nombre:
        raise ValueError("Grupo no indicado")
    if datos is None:
        datos = datos_sesion_evaluacion_grupo(nombre)
    # materia_label → contadores
    acc: dict[str, dict[str, int]] = {}
    for ficha in datos.get("alumnos") or []:
        for m in _materias_actuales_informe(ficha):
            label = (m.get("materia") or "").strip()
            if not label:
                continue
            bucket = _bucket_cualitativo(m.get("nota_acta"))
            if bucket is None:
                continue
            row = acc.setdefault(
                label,
                {"sb": 0, "nt": 0, "bi": 0, "su": 0, "sus": 0},
            )
            row[bucket] = row.get(bucket, 0) + 1

    filas = [
        {
            "materia": mat,
            "sobresalientes": c["sb"],
            "notables": c["nt"],
            "bienes": c["bi"],
            "suficientes": c["su"],
            "suspensos": c["sus"],
            "total": c["sb"] + c["nt"] + c["bi"] + c["su"] + c["sus"],
        }
        for mat, c in acc.items()
    ]
    filas.sort(key=lambda r: normalize_for_sort(r["materia"]))
    return {
        "grupo": nombre,
        "filas": filas,
        "n_alumnos": len(datos.get("alumnos") or []),
    }


def _nota_acta_numerica(texto: object) -> float | None:
    """Valor numérico de nota_acta para medias (ESO: IN=4 … SB=9)."""
    from db.competencias_evaluacion import (
        _NOTA_ACTA_ESO_A_NUM,
        codigo_nota_acta_eso,
    )

    t = str(texto or "").strip()
    if not t or t == "—":
        return None
    up = t.upper().replace("Í", "I")
    if up in _NOTA_ACTA_ESO_A_NUM:
        return float(_NOTA_ACTA_ESO_A_NUM[up])
    code = codigo_nota_acta_eso(t)
    if code in _NOTA_ACTA_ESO_A_NUM:
        return float(_NOTA_ACTA_ESO_A_NUM[code])
    n = _parse_nota_es(t)
    if n is None:
        return None
    return float(n)


def _fmt_media_1d(val: float) -> str:
    s = f"{val:.1f}".replace(".", ",")
    return s


def _abrev_materia(nombre: str, *, max_len: int = 10) -> str:
    s = (nombre or "").strip()
    if not s:
        return ""
    if len(s) <= max_len:
        return s
    parts = s.split()
    if len(parts) >= 2:
        corto = f"{parts[0]} {parts[1][0]}."
        if len(corto) <= max_len:
            return corto
    return s[: max_len - 1] + "…"


def _abrev_corta_materia(abrev: object, *, fallback_nombre: str = "") -> str:
    """``ESO-1-MAE`` → ``MAE`` para ejes de gráficos en informes."""
    s = str(abrev or "").strip()
    if "-" in s:
        return s.rsplit("-", 1)[-1].strip()
    if s:
        return s
    return _abrev_materia(fallback_nombre)


def _materias_actuales_informe(ficha: dict[str, Any]) -> list[dict[str, Any]]:
    """Materias del curso actual del alumno (sin pendientes de cursos anteriores)."""
    out: list[dict[str, Any]] = []
    for m in ficha.get("materias_curso") or []:
        if m.get("es_pendiente"):
            continue
        out.append(m)
    return out


def _media_materias_informe(
    ficha: dict[str, Any],
) -> tuple[float | None, int, int]:
    """Media acta, aprobados y suspensos solo con materias del curso actual."""
    nums: list[float] = []
    apr = sus = 0
    for m in _materias_actuales_informe(ficha):
        num = _nota_acta_numerica(m.get("nota_acta"))
        if num is None:
            continue
        nums.append(num)
        if _nota_acta_suspensa(m.get("nota_acta")):
            sus += 1
        else:
            apr += 1
    if not nums:
        return None, apr, sus
    return sum(nums) / len(nums), apr, sus


def _ranking_chart_meta(filas: list[dict[str, Any]]) -> float:
    """Añade abrev y bar_pct a cada fila; devuelve ymax del eje Y."""
    medias = [float(f["media"]) for f in filas if f.get("media") is not None]
    chart_ymax = max(10.0, math.ceil(max(medias) if medias else 10.0))
    for f in filas:
        abrev = (f.get("materia_abrev") or "").strip()
        f["abrev"] = _abrev_corta_materia(
            abrev, fallback_nombre=f.get("materia") or ""
        )
        media = float(f.get("media") or 0)
        f["bar_pct"] = (
            int(round(100.0 * media / chart_ymax)) if chart_ymax else 0
        )
    return chart_ymax


def build_informe_grupo_ranking(
    grupo: str, *, datos: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Ranking de materias por nota media (curso actual) en un grupo."""
    nombre = (grupo or "").strip()
    if not nombre:
        raise ValueError("Grupo no indicado")
    if datos is None:
        datos = datos_sesion_evaluacion_grupo(nombre)
    acc: dict[str, dict[str, Any]] = {}
    for ficha in datos.get("alumnos") or []:
        for m in _materias_actuales_informe(ficha):
            label = (m.get("materia") or "").strip()
            if not label:
                continue
            num = _nota_acta_numerica(m.get("nota_acta"))
            if num is None:
                continue
            row = acc.setdefault(
                label,
                {
                    "suma": 0.0,
                    "n": 0,
                    "aprobados": 0,
                    "suspensos": 0,
                    "materia_abrev": "",
                },
            )
            abrev = (m.get("materia_abrev") or "").strip()
            if abrev and not row["materia_abrev"]:
                row["materia_abrev"] = abrev
            row["suma"] += num
            row["n"] += 1
            if _nota_acta_suspensa(m.get("nota_acta")):
                row["suspensos"] += 1
            else:
                row["aprobados"] += 1

    filas: list[dict[str, Any]] = []
    for mat, c in acc.items():
        n = int(c["n"])
        if n <= 0:
            continue
        media = float(c["suma"]) / n
        apr = int(c["aprobados"])
        sus = int(c["suspensos"])
        filas.append(
            {
                "materia": mat,
                "materia_abrev": (c.get("materia_abrev") or "").strip(),
                "media": media,
                "media_display": _fmt_media_1d(media),
                "aprobados": apr,
                "aprobados_pct": _pct(apr, n),
                "suspensos": sus,
                "suspensos_pct": _pct(sus, n),
                "n": n,
            }
        )
    filas.sort(
        key=lambda r: (-r["media"], normalize_for_sort(r["materia"]))
    )
    chart_ymax = _ranking_chart_meta(filas)
    return {
        "grupo": nombre,
        "filas": filas,
        "n_alumnos": len(datos.get("alumnos") or []),
        "chart_ymax": chart_ymax,
    }


def build_informe_grupo_competencias(
    grupo: str, *, datos: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Nota media / aprobados / suspensos por competencia clave (orden LOMLOE)."""
    from db.competencias_clave import COMPETENCIAS_CLAVE_SEED

    nombre = (grupo or "").strip()
    if not nombre:
        raise ValueError("Grupo no indicado")
    if datos is None:
        datos = datos_sesion_evaluacion_grupo(nombre)
    # abrev → acumulados
    acc: dict[str, dict[str, Any]] = {
        c["abreviatura"]: {
            "nombre": c["nombre"],
            "suma": 0.0,
            "n": 0,
            "aprobados": 0,
            "suspensos": 0,
        }
        for c in COMPETENCIAS_CLAVE_SEED
    }
    for ficha in datos.get("alumnos") or []:
        for fila in ficha.get("competencias") or []:
            abrev = (fila.get("abreviatura") or "").strip()
            if abrev not in acc:
                continue
            # Media con decimales (nota_2d); aprobación con nota entera de sesión.
            if fila.get("editada_sesion"):
                num = _parse_nota_es(fila.get("nota"))
            else:
                num = _parse_nota_es(fila.get("nota_2d"))
                if num is None:
                    num = _parse_nota_es(fila.get("nota"))
            if num is None:
                continue
            entera = _parse_nota_es(fila.get("nota"))
            if entera is None:
                entera = num
            row = acc[abrev]
            row["suma"] += float(num)
            row["n"] += 1
            if _es_suspensa(entera):
                row["suspensos"] += 1
            else:
                row["aprobados"] += 1

    filas: list[dict[str, Any]] = []
    for c in COMPETENCIAS_CLAVE_SEED:
        abrev = c["abreviatura"]
        row = acc[abrev]
        n = int(row["n"])
        if n > 0:
            media = float(row["suma"]) / n
            media_display = _fmt_media_1d(media)
            apr = int(row["aprobados"])
            sus = int(row["suspensos"])
            apr_pct = _pct(apr, n)
            sus_pct = _pct(sus, n)
        else:
            media = None
            media_display = "—"
            apr = sus = 0
            apr_pct = sus_pct = 0
        filas.append(
            {
                "abreviatura": abrev,
                "nombre": c["nombre"],
                "label": f"{abrev} · {c['nombre']}",
                "media": media,
                "media_display": media_display,
                "aprobados": apr,
                "aprobados_pct": apr_pct,
                "suspensos": sus,
                "suspensos_pct": sus_pct,
                "n": n,
            }
        )
    return {
        "grupo": nombre,
        "filas": filas,
        "n_alumnos": len(datos.get("alumnos") or []),
    }


def _categoria_decision_detalle(ficha: dict[str, Any]) -> str | None:
    """promo | excepcional | pil | repetir | None si no hay decisión."""
    dec = (ficha.get("decision") or "").strip().upper()
    if not dec:
        return None
    if ficha.get("es_pil") or "PIL" in dec:
        return "pil"
    if ficha.get("decision_ok") is True:
        if ficha.get("excepcionalidad"):
            return "excepcional"
        return "promo"
    if ficha.get("decision_ok") is False or "NO " in dec:
        return "repetir"
    if ficha.get("excepcionalidad"):
        return "excepcional"
    return "promo"


DECISION_PIE_COLORS: dict[str, str] = {
    "promo": "#73c759",
    "excepcional": "#59a6f2",
    "pil": "#f2d140",
    "repetir": "#f28c38",
}


def _decision_meta(etapa: str, curso_num: int | None) -> dict[str, Any]:
    es_titulacion = (etapa == "eso" and curso_num == 4) or (
        etapa == "bach" and curso_num == 2
    )
    muestra_pil = etapa == "eso" and curso_num in (1, 2, 3)
    muestra_excepcional = muestra_pil or (etapa == "bach" and curso_num == 2)
    if es_titulacion:
        labels = {
            "promo": "Titula",
            "excepcional": "Titulación excepcional",
            "pil": "PIL",
            "repetir": "No titula",
        }
        titulo_bloque = "Titulación"
    else:
        labels = {
            "promo": "Promoción",
            "excepcional": "Promoción excepcional",
            "pil": "PIL",
            "repetir": "No promociona",
        }
        titulo_bloque = "Promoción"
    order: list[str] = ["promo"]
    if muestra_excepcional:
        order.append("excepcional")
    if muestra_pil:
        order.append("pil")
    order.append("repetir")
    return {
        "labels": labels,
        "order": order,
        "titulo_bloque": titulo_bloque,
        "es_titulacion": es_titulacion,
        "muestra_pil": muestra_pil,
        "muestra_excepcional": muestra_excepcional,
    }


def _contar_decisiones(
    datos: dict[str, Any],
    order: list[str],
) -> tuple[dict[str, int], int]:
    cat = {k: 0 for k in order}
    sin_decision = 0
    for ficha in datos.get("alumnos") or []:
        c = _categoria_decision_detalle(ficha)
        if c is None:
            sin_decision += 1
            continue
        if c not in cat:
            if c == "pil":
                cat["promo"] = cat.get("promo", 0) + 1
            elif c == "excepcional" and "excepcional" not in cat:
                cat["promo"] = cat.get("promo", 0) + 1
            else:
                cat["repetir"] = cat.get("repetir", 0) + 1
            continue
        cat[c] += 1
    return cat, sin_decision


def _filas_decision_tabla(
    cat: dict[str, int],
    *,
    order: list[str],
    labels: dict[str, str],
    den: int,
    grupos_curso: list[str],
    por_grupo: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    filas: list[dict[str, Any]] = []
    for k in order:
        filas.append(
            {
                "key": k,
                "label": labels[k],
                "n": cat[k],
                "pct": _pct(cat[k], den),
                "color": DECISION_PIE_COLORS.get(k, "#999999"),
                "grupos": {
                    g: int(por_grupo.get(g, {}).get(k, 0)) for g in grupos_curso
                },
            }
        )
    return filas


def _pie_conic_gradient(filas: list[dict[str, Any]]) -> str:
    slices = [f for f in filas if int(f.get("n") or 0) > 0]
    if not slices:
        return ""
    total = sum(int(f["n"]) for f in slices)
    parts: list[str] = []
    acc = 0.0
    for f in slices:
        pct = 100.0 * int(f["n"]) / total
        color = f.get("color") or DECISION_PIE_COLORS.get(f.get("key", ""), "#999")
        parts.append(f"{color} {acc:.2f}% {acc + pct:.2f}%")
        acc += pct
    return f"conic-gradient({', '.join(parts)})"


def build_informe_grupo_decision(
    grupo: str,
    *,
    datos: dict[str, Any] | None = None,
    datos_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resumen de decisiones finales de evaluación del grupo (nº y %)."""
    nombre = (grupo or "").strip()
    if not nombre:
        raise ValueError("Grupo no indicado")
    if datos is None:
        if datos_map and nombre in datos_map:
            datos = datos_map[nombre]
        else:
            datos = datos_sesion_evaluacion_grupo(nombre)
    curso = get_group_curso(nombre)
    stage = stage_of(grupo=nombre, curso=curso)
    curso_num = (
        extract_course_num(grupo=nombre, curso=curso, stage=stage) if stage else None
    )
    etapa = "bach" if stage == "bachillerato" else ("eso" if stage == "eso" else "")
    meta = _decision_meta(etapa, curso_num)
    order = meta["order"]
    labels = meta["labels"]

    cat, sin_decision = _contar_decisiones(datos, order)
    den = sum(cat.values())

    grupos_curso: list[str] = []
    por_grupo: dict[str, dict[str, int]] = {}
    if etapa and curso_num is not None:
        grupos_curso = grupos_del_curso(etapa, curso_num)
        if len(grupos_curso) > 1:
            for g in grupos_curso:
                if datos_map and g in datos_map:
                    g_datos = datos_map[g]
                elif g == nombre:
                    g_datos = datos
                else:
                    g_datos = datos_sesion_evaluacion_grupo(g)
                g_cat, _ = _contar_decisiones(g_datos, order)
                por_grupo[g] = g_cat

    filas = _filas_decision_tabla(
        cat,
        order=order,
        labels=labels,
        den=den,
        grupos_curso=grupos_curso,
        por_grupo=por_grupo,
    )
    return {
        "grupo": nombre,
        "titulo_bloque": meta["titulo_bloque"],
        "es_titulacion": meta["es_titulacion"],
        "muestra_pil": meta["muestra_pil"],
        "muestra_excepcional": meta["muestra_excepcional"],
        "filas": filas,
        "grupos_curso": grupos_curso,
        "pie_gradient": _pie_conic_gradient(filas),
        "n_alumnos": len(datos.get("alumnos") or []),
        "n_con_decision": den,
        "sin_decision": sin_decision,
        "denominador": den,
    }


def build_informe_grupo_alumnos(
    grupo: str, *, datos: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Alumnos del grupo ordenados por media de competencias."""
    nombre = (grupo or "").strip()
    if not nombre:
        raise ValueError("Grupo no indicado")
    if datos is None:
        datos = datos_sesion_evaluacion_grupo(nombre)
    filas: list[dict[str, Any]] = []
    for ficha in datos.get("alumnos") or []:
        media_cc = _parse_nota_es(ficha.get("media_competencias"))

        apr_c = sus_c = 0
        for c in ficha.get("competencias") or []:
            if c.get("editada_sesion"):
                num = _parse_nota_es(c.get("nota"))
            else:
                num = _parse_nota_es(c.get("nota_2d"))
                if num is None:
                    num = _parse_nota_es(c.get("nota"))
            if num is None:
                continue
            entera = _parse_nota_es(c.get("nota"))
            if entera is None:
                entera = num
            if _es_suspensa(entera):
                sus_c += 1
            else:
                apr_c += 1

        media_mat, apr_m, sus_m = _media_materias_informe(ficha)

        dec = (ficha.get("decision") or "").strip()
        filas.append(
            {
                "alumno": (ficha.get("alumno") or "").strip(),
                "media_comp": float(media_cc) if media_cc is not None else None,
                "media_comp_display": (
                    _fmt_media_1d(float(media_cc)) if media_cc is not None else "—"
                ),
                "media_mat": float(media_mat) if media_mat is not None else None,
                "media_mat_display": (
                    _fmt_media_1d(float(media_mat)) if media_mat is not None else "—"
                ),
                "competencias_resumen": f"{apr_c}-{sus_c}",
                "materias_resumen": f"{apr_m}-{sus_m}",
                "decision": dec or "—",
                "decision_ok": ficha.get("decision_ok"),
            }
        )
    filas.sort(
        key=lambda r: (
            r["media_comp"] is None,
            -(r["media_comp"] if r["media_comp"] is not None else 0.0),
            normalize_for_sort(r["alumno"]),
        )
    )
    return {
        "grupo": nombre,
        "filas": filas,
        "n_alumnos": len(filas),
    }


def build_informe_grupo_completo(grupo: str) -> dict[str, Any]:
    """Datos de las 5 vistas de informe de grupo (una sola carga de sesión)."""
    nombre = (grupo or "").strip()
    if not nombre:
        raise ValueError("Grupo no indicado")
    datos = datos_sesion_evaluacion_grupo(nombre)
    return {
        "grupo": nombre,
        "curso_escolar": _school_year_short(),
        "materias": build_informe_grupo_materias(nombre, datos=datos),
        "ranking": build_informe_grupo_ranking(nombre, datos=datos),
        "competencias": build_informe_grupo_competencias(nombre, datos=datos),
        "decision": build_informe_grupo_decision(nombre, datos=datos),
        "alumnos": build_informe_grupo_alumnos(nombre, datos=datos),
    }


def _resolver_grupos_curso(sel: str) -> tuple[str, int, str, list[str]]:
    parsed = parse_curso_sel(sel)
    if not parsed:
        raise ValueError("Curso no válido")
    etapa, curso_num = parsed
    titulo = label_curso(etapa, curso_num)
    grupos = grupos_del_curso(etapa, curso_num)
    if not grupos:
        cols = grupos_para_evaluar(ver_todos=True)
        flat = [
            *(cols.get("eso_12") or []),
            *(cols.get("eso_34") or []),
            *(cols.get("bach") or []),
        ]
        for name in flat:
            curso = get_group_curso(name)
            st = stage_of(grupo=name, curso=curso)
            want = "eso" if etapa == "eso" else "bachillerato"
            if st != want:
                continue
            num = extract_course_num(grupo=name, curso=curso, stage=st)
            if num == curso_num:
                grupos.append(name)
        grupos = sorted(set(grupos), key=normalize_for_sort)
    return etapa, curso_num, titulo, grupos


def _datos_por_grupos(grupos: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for g in grupos:
        out[g] = datos_sesion_evaluacion_grupo(g)
    return out


SUSPENSOS_ALUMNO_ORDER = ("0_2", "3_4", "5_mas")
SUSPENSOS_ALUMNO_LABELS = {
    "0_2": "0 a 2 suspensos",
    "3_4": "3 o 4 suspensos",
    "5_mas": "5 o más suspensos",
}
SUSPENSOS_ALUMNO_COLORS = {
    "0_2": "#73c759",
    "3_4": "#f2d140",
    "5_mas": "#f28c38",
}


def _contexto_grupos_de_grupo(
    nombre: str, *, datos: dict[str, Any] | None = None
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Grupos del mismo curso (para comparar) y mapa de sesiones."""
    nombre = (nombre or "").strip()
    curso = get_group_curso(nombre)
    stage = stage_of(grupo=nombre, curso=curso)
    curso_num = (
        extract_course_num(grupo=nombre, curso=curso, stage=stage) if stage else None
    )
    etapa = "bach" if stage == "bachillerato" else ("eso" if stage == "eso" else "")
    grupos = [nombre]
    if etapa and curso_num is not None:
        gc = grupos_del_curso(etapa, curso_num)
        if gc:
            grupos = gc
        if nombre not in grupos:
            grupos = sorted([*grupos, nombre], key=normalize_for_sort)
    datos_map: dict[str, dict[str, Any]] = {}
    for g in grupos:
        if datos is not None and g == nombre:
            datos_map[g] = datos
        else:
            datos_map[g] = datos_sesion_evaluacion_grupo(g)
    return grupos, datos_map


def _stats_suspensos_por_grupo(
    grupos: list[str],
    datos_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in grupos:
        datos = datos_map.get(g) or {}
        alumnos = datos.get("alumnos") or []
        bucket = {k: 0 for k in SUSPENSOS_ALUMNO_ORDER}
        sum_sus = 0
        for ficha in alumnos:
            ns = _n_suspensos_ficha(ficha)
            sum_sus += ns
            if ns <= 2:
                bucket["0_2"] += 1
            elif ns <= 4:
                bucket["3_4"] += 1
            else:
                bucket["5_mas"] += 1
        n = len(alumnos)
        media = (sum_sus / n) if n else 0.0
        out.append(
            {
                "grupo": g,
                "alumnos": n,
                "bucket": bucket,
                "media": media,
                "media_display": _fmt_media(media),
                "stack": [
                    {
                        "key": k,
                        "n": bucket[k],
                        "pct": _pct(bucket[k], n),
                        "color": SUSPENSOS_ALUMNO_COLORS[k],
                    }
                    for k in SUSPENSOS_ALUMNO_ORDER
                ],
            }
        )
    return out


def _informe_suspensos_base(
    grupos: list[str],
    datos_map: dict[str, dict[str, Any]],
    *,
    titulo: str,
) -> dict[str, Any]:
    stats = _stats_suspensos_por_grupo(grupos, datos_map)
    n_alumnos = sum(int(s["alumnos"]) for s in stats)
    tot_b = {
        k: sum(int(s["bucket"][k]) for s in stats) for k in SUSPENSOS_ALUMNO_ORDER
    }
    sum_sus_all = sum(float(s["media"]) * int(s["alumnos"]) for s in stats)
    media_tot = (sum_sus_all / n_alumnos) if n_alumnos else 0.0
    total_col = {
        "grupo": "TOTAL",
        "alumnos": n_alumnos,
        "bucket": tot_b,
        "media": media_tot,
        "media_display": _fmt_media(media_tot),
        "stack": [
            {
                "key": k,
                "n": tot_b[k],
                "pct": _pct(tot_b[k], n_alumnos),
                "color": SUSPENSOS_ALUMNO_COLORS[k],
            }
            for k in SUSPENSOS_ALUMNO_ORDER
        ],
    }
    filas_alumno = [
        {
            "key": k,
            "label": SUSPENSOS_ALUMNO_LABELS[k],
            "n": tot_b[k],
            "pct": _pct(tot_b[k], n_alumnos),
            "color": SUSPENSOS_ALUMNO_COLORS[k],
            "grupos": {s["grupo"]: int(s["bucket"][k]) for s in stats},
        }
        for k in SUSPENSOS_ALUMNO_ORDER
    ]
    medias = [float(s["media"]) for s in stats] + [media_tot]
    chart_ymax = max(8.0, math.ceil(max(medias) if medias else 8.0))
    for s in stats:
        s["bar_pct"] = (
            int(round(100.0 * float(s["media"]) / chart_ymax)) if chart_ymax else 0
        )
    total_col["bar_pct"] = (
        int(round(100.0 * media_tot / chart_ymax)) if chart_ymax else 0
    )
    return {
        "grupo": titulo,
        "grupos_curso": grupos,
        "columnas_chart": stats + [total_col],
        "filas_alumno": filas_alumno,
        "stats": stats,
        "total": total_col,
        "pie_gradient": _pie_conic_gradient(filas_alumno),
        "n_alumnos": n_alumnos,
        "chart_ymax": chart_ymax,
    }


def _agregar_suspensos_por_cursos(
    stats: list[dict[str, Any]],
    *,
    etapa: str,
) -> dict[str, Any]:
    """Reagrupa estadísticas de grupos en columnas por curso (1º, 2º…)."""
    etapa_key = (etapa or "").strip().lower()
    stage = "eso" if etapa_key == "eso" else "bachillerato"
    etapa_db = "eso" if stage == "eso" else "bach"
    by_num: dict[int, dict[str, Any]] = {}
    for s in stats:
        g = str(s.get("grupo") or "").strip()
        if not g or g == "TOTAL":
            continue
        curso = get_group_curso(g)
        st = stage_of(grupo=g, curso=curso) or stage
        num = extract_course_num(grupo=g, curso=curso, stage=st)
        if num is None:
            continue
        row = by_num.setdefault(
            num,
            {
                "alumnos": 0,
                "bucket": {k: 0 for k in SUSPENSOS_ALUMNO_ORDER},
                "sum_sus": 0.0,
            },
        )
        n_al = int(s.get("alumnos") or 0)
        row["alumnos"] += n_al
        for k in SUSPENSOS_ALUMNO_ORDER:
            row["bucket"][k] += int((s.get("bucket") or {}).get(k) or 0)
        row["sum_sus"] += float(s.get("media") or 0) * n_al

    nums = sorted(by_num.keys())
    curso_labels = [label_curso(etapa_db, n) for n in nums]
    stats_curso: list[dict[str, Any]] = []
    for num, lab in zip(nums, curso_labels):
        cell = by_num[num]
        n = int(cell["alumnos"])
        media = (float(cell["sum_sus"]) / n) if n else 0.0
        bucket = cell["bucket"]
        stats_curso.append(
            {
                "grupo": lab,
                "alumnos": n,
                "bucket": bucket,
                "media": media,
                "media_display": _fmt_media(media),
                "stack": [
                    {
                        "key": k,
                        "n": bucket[k],
                        "pct": _pct(bucket[k], n),
                        "color": SUSPENSOS_ALUMNO_COLORS[k],
                    }
                    for k in SUSPENSOS_ALUMNO_ORDER
                ],
            }
        )
    n_alumnos = sum(int(s["alumnos"]) for s in stats_curso)
    tot_b = {
        k: sum(int(s["bucket"][k]) for s in stats_curso) for k in SUSPENSOS_ALUMNO_ORDER
    }
    sum_sus_all = sum(float(s["media"]) * int(s["alumnos"]) for s in stats_curso)
    media_tot = (sum_sus_all / n_alumnos) if n_alumnos else 0.0
    total_col = {
        "grupo": "TOTAL",
        "alumnos": n_alumnos,
        "bucket": tot_b,
        "media": media_tot,
        "media_display": _fmt_media(media_tot),
        "stack": [
            {
                "key": k,
                "n": tot_b[k],
                "pct": _pct(tot_b[k], n_alumnos),
                "color": SUSPENSOS_ALUMNO_COLORS[k],
            }
            for k in SUSPENSOS_ALUMNO_ORDER
        ],
    }
    filas_alumno = [
        {
            "key": k,
            "label": SUSPENSOS_ALUMNO_LABELS[k],
            "n": tot_b[k],
            "pct": _pct(tot_b[k], n_alumnos),
            "color": SUSPENSOS_ALUMNO_COLORS[k],
            "grupos": {s["grupo"]: int(s["bucket"][k]) for s in stats_curso},
        }
        for k in SUSPENSOS_ALUMNO_ORDER
    ]
    medias = [float(s["media"]) for s in stats_curso] + [media_tot]
    chart_ymax = max(8.0, math.ceil(max(medias) if medias else 8.0))
    for s in stats_curso:
        s["bar_pct"] = (
            int(round(100.0 * float(s["media"]) / chart_ymax)) if chart_ymax else 0
        )
    total_col["bar_pct"] = (
        int(round(100.0 * media_tot / chart_ymax)) if chart_ymax else 0
    )
    return {
        "grupos_curso": curso_labels,
        "columnas_chart": stats_curso + [total_col],
        "filas_alumno": filas_alumno,
        "stats": stats_curso,
        "total": total_col,
        "pie_gradient": _pie_conic_gradient(filas_alumno),
        "n_alumnos": n_alumnos,
        "chart_ymax": chart_ymax,
    }


def build_informe_grupo_suspensos_alumno(
    grupo: str, *, datos: dict[str, Any] | None = None
) -> dict[str, Any]:
    nombre = (grupo or "").strip()
    if not nombre:
        raise ValueError("Grupo no indicado")
    grupos, datos_map = _contexto_grupos_de_grupo(nombre, datos=datos)
    return _informe_suspensos_base(grupos, datos_map, titulo=nombre)


def build_informe_grupo_suspensos_grupo(
    grupo: str, *, datos: dict[str, Any] | None = None
) -> dict[str, Any]:
    return build_informe_grupo_suspensos_alumno(grupo, datos=datos)


def build_informe_curso_suspensos_alumno(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    _etapa, _num, titulo, grupos = _resolver_grupos_curso(sel)
    if datos_map is None:
        datos_map = _datos_por_grupos(grupos)
    return _informe_suspensos_base(grupos, datos_map, titulo=titulo)


def build_informe_curso_suspensos_grupo(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    return build_informe_curso_suspensos_alumno(sel, datos_map=datos_map)


def build_informe_etapa_suspensos_alumno(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    etapa = (sel or "").strip().lower()
    if etapa not in {"eso", "bachillerato"}:
        raise ValueError("Etapa no válida")
    grupos = grupos_de_etapa(etapa)
    if not grupos:
        raise ValueError("No hay grupos en esta etapa")
    if datos_map is None:
        datos_map = _datos_por_grupos(grupos)
    else:
        missing = [g for g in grupos if g not in datos_map]
        if missing:
            extra = _datos_por_grupos(missing)
            datos_map = {**datos_map, **extra}
    titulo = "ESO" if etapa == "eso" else "Bachillerato"
    out = _informe_suspensos_base(grupos, datos_map, titulo=titulo)
    out["curso_escolar"] = _school_year_short()
    out["por_curso"] = _agregar_suspensos_por_cursos(out["stats"], etapa=etapa)
    return out


def build_informe_etapa_suspensos_grupo(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    return build_informe_etapa_suspensos_alumno(sel, datos_map=datos_map)


def build_informe_curso_materias(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Distribución de nota_acta por materia agregada en todo el curso."""
    _etapa, _num, titulo, grupos = _resolver_grupos_curso(sel)
    if datos_map is None:
        datos_map = _datos_por_grupos(grupos)
    acc: dict[str, dict[str, int]] = {}
    n_alumnos = 0
    for g in grupos:
        datos = datos_map.get(g) or {}
        n_alumnos += len(datos.get("alumnos") or [])
        part = build_informe_grupo_materias(g, datos=datos)
        for f in part.get("filas") or []:
            mat = f["materia"]
            row = acc.setdefault(
                mat,
                {"sb": 0, "nt": 0, "bi": 0, "su": 0, "sus": 0},
            )
            row["sb"] += int(f.get("sobresalientes") or 0)
            row["nt"] += int(f.get("notables") or 0)
            row["bi"] += int(f.get("bienes") or 0)
            row["su"] += int(f.get("suficientes") or 0)
            row["sus"] += int(f.get("suspensos") or 0)
    filas = [
        {
            "materia": mat,
            "sobresalientes": c["sb"],
            "notables": c["nt"],
            "bienes": c["bi"],
            "suficientes": c["su"],
            "suspensos": c["sus"],
            "total": c["sb"] + c["nt"] + c["bi"] + c["su"] + c["sus"],
        }
        for mat, c in acc.items()
    ]
    filas.sort(key=lambda r: normalize_for_sort(r["materia"]))
    return {"grupo": titulo, "filas": filas, "n_alumnos": n_alumnos}


def build_informe_curso_ranking(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    _etapa, _num, titulo, grupos = _resolver_grupos_curso(sel)
    if datos_map is None:
        datos_map = _datos_por_grupos(grupos)
    acc: dict[str, dict[str, Any]] = {}
    n_alumnos = 0
    for g in grupos:
        datos = datos_map.get(g) or {}
        n_alumnos += len(datos.get("alumnos") or [])
        for ficha in datos.get("alumnos") or []:
            for m in _materias_actuales_informe(ficha):
                label = (m.get("materia") or "").strip()
                if not label:
                    continue
                num = _nota_acta_numerica(m.get("nota_acta"))
                if num is None:
                    continue
                row = acc.setdefault(
                    label,
                    {
                        "suma": 0.0,
                        "n": 0,
                        "aprobados": 0,
                        "suspensos": 0,
                        "materia_abrev": "",
                    },
                )
                abrev = (m.get("materia_abrev") or "").strip()
                if abrev and not row["materia_abrev"]:
                    row["materia_abrev"] = abrev
                row["suma"] += num
                row["n"] += 1
                if _nota_acta_suspensa(m.get("nota_acta")):
                    row["suspensos"] += 1
                else:
                    row["aprobados"] += 1
    filas: list[dict[str, Any]] = []
    for mat, c in acc.items():
        n = int(c["n"])
        if n <= 0:
            continue
        media = float(c["suma"]) / n
        apr = int(c["aprobados"])
        sus = int(c["suspensos"])
        filas.append(
            {
                "materia": mat,
                "materia_abrev": (c.get("materia_abrev") or "").strip(),
                "media": media,
                "media_display": _fmt_media_1d(media),
                "aprobados": apr,
                "aprobados_pct": _pct(apr, n),
                "suspensos": sus,
                "suspensos_pct": _pct(sus, n),
                "n": n,
            }
        )
    filas.sort(key=lambda r: (-r["media"], normalize_for_sort(r["materia"])))
    chart_ymax = _ranking_chart_meta(filas)
    return {
        "grupo": titulo,
        "filas": filas,
        "n_alumnos": n_alumnos,
        "chart_ymax": chart_ymax,
    }


def build_informe_curso_competencias(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    from db.competencias_clave import COMPETENCIAS_CLAVE_SEED

    _etapa, _num, titulo, grupos = _resolver_grupos_curso(sel)
    if datos_map is None:
        datos_map = _datos_por_grupos(grupos)
    acc: dict[str, dict[str, Any]] = {
        c["abreviatura"]: {
            "nombre": c["nombre"],
            "suma": 0.0,
            "n": 0,
            "aprobados": 0,
            "suspensos": 0,
        }
        for c in COMPETENCIAS_CLAVE_SEED
    }
    n_alumnos = 0
    for g in grupos:
        datos = datos_map.get(g) or {}
        n_alumnos += len(datos.get("alumnos") or [])
        for ficha in datos.get("alumnos") or []:
            for fila in ficha.get("competencias") or []:
                abrev = (fila.get("abreviatura") or "").strip()
                if abrev not in acc:
                    continue
                if fila.get("editada_sesion"):
                    num = _parse_nota_es(fila.get("nota"))
                else:
                    num = _parse_nota_es(fila.get("nota_2d"))
                    if num is None:
                        num = _parse_nota_es(fila.get("nota"))
                if num is None:
                    continue
                entera = _parse_nota_es(fila.get("nota"))
                if entera is None:
                    entera = num
                row = acc[abrev]
                row["suma"] += float(num)
                row["n"] += 1
                if _es_suspensa(entera):
                    row["suspensos"] += 1
                else:
                    row["aprobados"] += 1
    filas: list[dict[str, Any]] = []
    for c in COMPETENCIAS_CLAVE_SEED:
        abrev = c["abreviatura"]
        row = acc[abrev]
        n = int(row["n"])
        if n > 0:
            media = float(row["suma"]) / n
            media_display = _fmt_media_1d(media)
            apr = int(row["aprobados"])
            sus = int(row["suspensos"])
            apr_pct = _pct(apr, n)
            sus_pct = _pct(sus, n)
        else:
            media = None
            media_display = "—"
            apr = sus = 0
            apr_pct = sus_pct = 0
        filas.append(
            {
                "abreviatura": abrev,
                "nombre": c["nombre"],
                "label": f"{abrev} · {c['nombre']}",
                "media": media,
                "media_display": media_display,
                "aprobados": apr,
                "aprobados_pct": apr_pct,
                "suspensos": sus,
                "suspensos_pct": sus_pct,
                "n": n,
            }
        )
    return {"grupo": titulo, "filas": filas, "n_alumnos": n_alumnos}


def build_informe_curso_decision(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    etapa, curso_num, titulo, grupos = _resolver_grupos_curso(sel)
    if datos_map is None:
        datos_map = _datos_por_grupos(grupos)
    # Misma estructura de categorías que un grupo del curso
    base = None
    for g in grupos:
        base = build_informe_grupo_decision(g, datos=datos_map.get(g))
        break
    if base is None:
        # Curso sin grupos: estructura vacía vía un grupo ficticio no sirve;
        # construir a mano con flags del curso.
        es_titulacion = (etapa == "eso" and curso_num == 4) or (
            etapa == "bach" and curso_num == 2
        )
        muestra_pil = etapa == "eso" and curso_num in (1, 2, 3)
        muestra_excepcional = muestra_pil or (etapa == "bach" and curso_num == 2)
        if es_titulacion:
            labels = {
                "promo": "Titula",
                "excepcional": "Titulación excepcional",
                "pil": "PIL",
                "repetir": "No titula",
            }
            titulo_bloque = "Titulación"
        else:
            labels = {
                "promo": "Promoción",
                "excepcional": "Promoción excepcional",
                "pil": "PIL",
                "repetir": "No promociona",
            }
            titulo_bloque = "Promoción"
        order = ["promo"]
        if muestra_excepcional:
            order.append("excepcional")
        if muestra_pil:
            order.append("pil")
        order.append("repetir")
        return {
            "grupo": titulo,
            "titulo_bloque": titulo_bloque,
            "es_titulacion": es_titulacion,
            "muestra_pil": muestra_pil,
            "muestra_excepcional": muestra_excepcional,
            "filas": [
                {
                    "key": k,
                    "label": labels[k],
                    "n": 0,
                    "pct": 0,
                    "color": DECISION_PIE_COLORS.get(k, "#999"),
                    "grupos": {},
                }
                for k in order
            ],
            "grupos_curso": [],
            "pie_gradient": "",
            "n_alumnos": 0,
            "n_con_decision": 0,
            "sin_decision": 0,
            "denominador": 0,
        }

    cat = {f["key"]: 0 for f in base["filas"]}
    n_alumnos = 0
    sin_decision = 0
    order = [f["key"] for f in base["filas"]]
    labels = {f["key"]: f["label"] for f in base["filas"]}
    por_grupo: dict[str, dict[str, int]] = {}
    for g in grupos:
        g_datos = datos_map.get(g) or {}
        n_alumnos += len(g_datos.get("alumnos") or [])
        g_cat, g_sin = _contar_decisiones(g_datos, order)
        sin_decision += g_sin
        por_grupo[g] = g_cat
        for k in order:
            cat[k] += g_cat.get(k, 0)
    den = sum(cat.values())
    filas = _filas_decision_tabla(
        cat,
        order=order,
        labels=labels,
        den=den,
        grupos_curso=grupos,
        por_grupo=por_grupo,
    )
    return {
        "grupo": titulo,
        "titulo_bloque": base["titulo_bloque"],
        "es_titulacion": base["es_titulacion"],
        "muestra_pil": base["muestra_pil"],
        "muestra_excepcional": base["muestra_excepcional"],
        "filas": filas,
        "grupos_curso": grupos,
        "pie_gradient": _pie_conic_gradient(filas),
        "n_alumnos": n_alumnos,
        "n_con_decision": den,
        "sin_decision": sin_decision,
        "denominador": den,
    }


def build_informe_curso_alumnos(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    _etapa, _num, titulo, grupos = _resolver_grupos_curso(sel)
    if datos_map is None:
        datos_map = _datos_por_grupos(grupos)
    filas: list[dict[str, Any]] = []
    for g in grupos:
        part = build_informe_grupo_alumnos(g, datos=datos_map.get(g))
        for f in part.get("filas") or []:
            filas.append({**f, "grupo": g})
    filas.sort(
        key=lambda r: (
            r["media_comp"] is None,
            -(r["media_comp"] if r["media_comp"] is not None else 0.0),
            normalize_for_sort(r.get("grupo") or ""),
            normalize_for_sort(r["alumno"]),
        )
    )
    return {"grupo": titulo, "filas": filas, "n_alumnos": len(filas)}


def build_informe_curso_completo(
    sel: str, *, datos_map: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Datos de las 5 vistas de informe de curso (una carga por grupo)."""
    _etapa, _num, titulo, grupos = _resolver_grupos_curso(sel)
    if datos_map is None:
        datos_map = _datos_por_grupos(grupos)
    return {
        "grupo": titulo,
        "ambito_label": "Curso",
        "sel": (sel or "").strip().lower(),
        "curso_escolar": _school_year_short(),
        "grupos": grupos,
        "materias": build_informe_curso_materias(sel, datos_map=datos_map),
        "ranking": build_informe_curso_ranking(sel, datos_map=datos_map),
        "competencias": build_informe_curso_competencias(sel, datos_map=datos_map),
        "decision": build_informe_curso_decision(sel, datos_map=datos_map),
        "alumnos": build_informe_curso_alumnos(sel, datos_map=datos_map),
    }


def parse_curso_sel(sel: str) -> tuple[str, int] | None:
    """``eso:1`` / ``bach:2`` → (etapa_db, curso_num)."""
    raw = (sel or "").strip().lower()
    if ":" not in raw:
        return None
    etapa, _, num_s = raw.partition(":")
    if etapa not in {"eso", "bach"}:
        return None
    try:
        num = int(num_s)
    except ValueError:
        return None
    if etapa == "eso" and num not in (1, 2, 3, 4):
        return None
    if etapa == "bach" and num not in (1, 2):
        return None
    return etapa, num


def label_curso(etapa: str, curso_num: int) -> str:
    if etapa == "eso":
        return f"{curso_num}º ESO"
    return f"{curso_num}º Bachillerato"


def _school_year_short() -> str:
    cal = get_latest_calendar()
    raw = str((cal or {}).get("school_year") or "").strip()
    if not raw:
        from utils.time_madrid import today_madrid

        today = today_madrid()
        y = today.year
        if today.month < 9:
            y -= 1
        return f"{str(y)[2:]}-{str(y + 1)[2:]}"
    # "2025-2026" → "25-26"; "25-26" se deja
    parts = [p.strip() for p in raw.replace("/", "-").split("-") if p.strip()]
    if len(parts) >= 2 and len(parts[0]) == 4 and len(parts[1]) == 4:
        return f"{parts[0][2:]}-{parts[1][2:]}"
    return raw


def grupos_del_curso(etapa: str, curso_num: int) -> list[str]:
    stage = "eso" if etapa == "eso" else "bachillerato"
    out: list[str] = []
    for g in list_groups_with_course():
        name = (g.get("name") or "").strip()
        if not name:
            continue
        curso = (g.get("curso") or "").strip() or None
        st = stage_of(grupo=name, curso=curso)
        if st != stage:
            continue
        num = extract_course_num(grupo=name, curso=curso, stage=st)
        if num == curso_num:
            out.append(name)
    out.sort(key=normalize_for_sort)
    return out


def grupos_de_etapa(etapa: str) -> list[str]:
    """Todos los grupos de ESO o Bachillerato."""
    stage = "eso" if (etapa or "").strip().lower() == "eso" else "bachillerato"
    out: list[str] = []
    for g in list_groups_with_course():
        name = (g.get("name") or "").strip()
        if not name:
            continue
        curso = (g.get("curso") or "").strip() or None
        st = stage_of(grupo=name, curso=curso)
        if st == stage:
            out.append(name)
    out.sort(key=normalize_for_sort)
    return out


def _nota_acta_suspensa(texto: object) -> bool:
    t = str(texto or "").strip()
    if not t or t == "—":
        return True
    up = t.upper()
    if up == "IN":
        return True
    if up in {"SU", "BI", "NT", "SB"}:
        return False
    return _es_suspensa(_parse_nota_es(t))


def _n_suspensos_ficha(ficha: dict[str, Any]) -> int:
    n = 0
    for m in _materias_actuales_informe(ficha):
        if _nota_acta_suspensa(m.get("nota_acta")):
            n += 1
    return n


def _categoria_promocion(ficha: dict[str, Any], *, etapa: str, curso_num: int) -> str | None:
    """promo | pil | repetir | None si no hay decisión."""
    dec = (ficha.get("decision") or "").strip().upper()
    if not dec:
        return None
    if ficha.get("es_pil") or "PIL" in dec:
        return "pil"
    ok = ficha.get("decision_ok")
    if ok is True:
        return "promo"
    if ok is False:
        return "repetir"
    if "NO " in dec:
        return "repetir"
    return "promo"


def _pct(n: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(round(100.0 * n / total))


def _fmt_media(val: float) -> str:
    s = f"{val:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _grupo_corto(nombre: str, curso_num: int) -> str:
    """1A → 1º A; 5B → 1º B en Bach (curso_num ya es 1/2)."""
    g = (nombre or "").strip()
    if len(g) >= 2 and g[0].isdigit():
        letra = g[1:].strip()
        return f"{curso_num}º {letra}"
    return g


def build_informe_curso(sel: str) -> dict[str, Any]:
    parsed = parse_curso_sel(sel)
    if not parsed:
        raise ValueError("Curso no válido")
    etapa, curso_num = parsed
    titulo = label_curso(etapa, curso_num)
    grupos = grupos_del_curso(etapa, curso_num)
    if not grupos:
        # Fallback: columnas de evaluar
        cols = grupos_para_evaluar(ver_todos=True)
        flat = [
            *(cols.get("eso_12") or []),
            *(cols.get("eso_34") or []),
            *(cols.get("bach") or []),
        ]
        for name in flat:
            curso = get_group_curso(name)
            st = stage_of(grupo=name, curso=curso)
            want = "eso" if etapa == "eso" else "bachillerato"
            if st != want:
                continue
            num = extract_course_num(grupo=name, curso=curso, stage=st)
            if num == curso_num:
                grupos.append(name)
        grupos = sorted(set(grupos), key=normalize_for_sort)

    por_grupo: dict[str, dict[str, Any]] = {}
    # materia_key → {abrev, label, aprobados, total}
    mat_stats: dict[str, dict[str, Any]] = {}

    for g in grupos:
        datos = datos_sesion_evaluacion_grupo(g)
        alumnos = datos.get("alumnos") or []
        n_al = len(alumnos)
        bucket = {"0_2": 0, "3_4": 0, "5_mas": 0}
        sum_sus = 0
        cat = {"promo": 0, "pil": 0, "repetir": 0}
        for ficha in alumnos:
            ns = _n_suspensos_ficha(ficha)
            sum_sus += ns
            if ns <= 2:
                bucket["0_2"] += 1
            elif ns <= 4:
                bucket["3_4"] += 1
            else:
                bucket["5_mas"] += 1
            c = _categoria_promocion(ficha, etapa=etapa, curso_num=curso_num)
            if c:
                cat[c] += 1
            for m in _materias_actuales_informe(ficha):
                key = (m.get("materia_key") or "").strip()
                if not key:
                    continue
                abrev = (m.get("materia_abrev") or "").strip().upper()
                if not abrev:
                    abrev = key[:6].upper()
                st = mat_stats.setdefault(
                    key,
                    {
                        "abrev": abrev,
                        "label": (m.get("materia") or abrev).strip(),
                        "aprobados": 0,
                        "total": 0,
                    },
                )
                if not st.get("abrev") and abrev:
                    st["abrev"] = abrev
                st["total"] += 1
                if not _nota_acta_suspensa(m.get("nota_acta")):
                    st["aprobados"] += 1
        media = (sum_sus / n_al) if n_al else 0.0
        por_grupo[g] = {
            "grupo": g,
            "label": _grupo_corto(g, curso_num),
            "alumnos": n_al,
            "bucket": bucket,
            "media_suspensos": media,
            "categorias": cat,
        }

    total_al = sum(g["alumnos"] for g in por_grupo.values())
    tot_b = {
        k: sum(g["bucket"][k] for g in por_grupo.values())
        for k in ("0_2", "3_4", "5_mas")
    }
    sum_sus_all = sum(
        g["media_suspensos"] * g["alumnos"] for g in por_grupo.values()
    )
    media_tot = (sum_sus_all / total_al) if total_al else 0.0
    cat_tot = {
        k: sum(g["categorias"][k] for g in por_grupo.values())
        for k in ("promo", "pil", "repetir")
    }
    den_promo = cat_tot["promo"] + cat_tot["pil"] + cat_tot["repetir"]

    es_titulacion = (etapa == "eso" and curso_num == 4) or (
        etapa == "bach" and curso_num == 2
    )
    muestra_pil = etapa == "eso" and curso_num in (1, 2, 3)

    grupos_orden = [por_grupo[g] for g in grupos if g in por_grupo]
    medias = [g["media_suspensos"] for g in grupos_orden] + [media_tot]
    chart_ymax = max(8.0, math.ceil(max(medias) if medias else 8.0))

    materias_aprobados: list[dict[str, Any]] = []
    for st in mat_stats.values():
        tot = int(st["total"])
        if tot <= 0:
            continue
        apr = int(st["aprobados"])
        pct = int(round(100.0 * apr / tot))
        materias_aprobados.append(
            {
                "abrev": st["abrev"],
                "label": st["label"],
                "aprobados": apr,
                "total": tot,
                "pct": pct,
            }
        )
    materias_aprobados.sort(key=lambda x: (-x["pct"], normalize_for_sort(x["abrev"])))

    return {
        "sel": f"{etapa}:{curso_num}",
        "etapa": etapa,
        "curso_num": curso_num,
        "titulo": titulo,
        "curso_escolar": _school_year_short(),
        "es_titulacion": es_titulacion,
        "muestra_pil": muestra_pil,
        "grupos": grupos_orden,
        "chart_ymax": chart_ymax,
        "materias_aprobados": materias_aprobados,
        "total": {
            "alumnos": total_al,
            "bucket": tot_b,
            "bucket_pct": {
                "0_2": _pct(tot_b["0_2"], total_al),
                "3_4": _pct(tot_b["3_4"], total_al),
                "5_mas": _pct(tot_b["5_mas"], total_al),
            },
            "media_suspensos": media_tot,
            "categorias": cat_tot,
            "categorias_pct": {
                "promo": _pct(cat_tot["promo"], den_promo),
                "pil": _pct(cat_tot["pil"], den_promo),
                "repetir": _pct(cat_tot["repetir"], den_promo),
            },
            "den_promocion": den_promo,
        },
        "fmt_media": _fmt_media,
    }


def recalcular_informes_cache() -> dict[str, Any]:
    """Precalcula todos los informes de grupo/curso/etapa y los guarda en BD.

    Carga la sesión de cada grupo una sola vez y reutiliza esos datos
    para vistas de grupo, curso y etapa (evita minutos de recálculos).
    """
    from db.competencias_informes_cache import (
        clear_informes_cache,
        latest_informes_cache_at,
        save_informe_cache,
    )

    clear_informes_cache()
    n_ok = 0
    errors: list[str] = []

    cols = grupos_para_evaluar(ver_todos=True)
    grupos = sorted(
        {
            *(cols.get("eso_12") or []),
            *(cols.get("eso_34") or []),
            *(cols.get("bach") or []),
        },
        key=normalize_for_sort,
    )

    datos_all: dict[str, dict[str, Any]] = {}
    for g in grupos:
        try:
            datos_all[g] = datos_sesion_evaluacion_grupo(g)
        except Exception as exc:
            errors.append(f"carga {g}: {exc}")

    for g in grupos:
        datos = datos_all.get(g)
        if datos is None:
            continue
        try:
            materias = build_informe_grupo_materias(g, datos=datos)
            ranking = build_informe_grupo_ranking(g, datos=datos)
            competencias = build_informe_grupo_competencias(g, datos=datos)
            decision = build_informe_grupo_decision(
                g, datos=datos, datos_map=datos_all
            )
            alumnos = build_informe_grupo_alumnos(g, datos=datos)
            for vista, payload in (
                ("materias", materias),
                ("ranking", ranking),
                ("competencias", competencias),
                ("decision", decision),
                ("alumnos", alumnos),
            ):
                save_informe_cache(ambito="grupo", sel=g, vista=vista, payload=payload)
                n_ok += 1
            save_informe_cache(
                ambito="grupo",
                sel=g,
                vista="completo",
                payload={
                    "grupo": g,
                    "curso_escolar": _school_year_short(),
                    "materias": materias,
                    "ranking": ranking,
                    "competencias": competencias,
                    "decision": decision,
                    "alumnos": alumnos,
                },
            )
            n_ok += 1
        except Exception as exc:
            errors.append(f"grupo {g}: {exc}")

    curso_sels: list[str] = []
    vistos: set[str] = set()
    for g in list_groups_with_course():
        name = (g.get("name") or "").strip()
        if not name:
            continue
        curso = (g.get("curso") or "").strip() or None
        st = stage_of(grupo=name, curso=curso)
        if st not in {"eso", "bachillerato"}:
            continue
        num = extract_course_num(grupo=name, curso=curso, stage=st)
        if num is None:
            continue
        key = f"{'eso' if st == 'eso' else 'bach'}:{num}"
        if key in vistos:
            continue
        vistos.add(key)
        curso_sels.append(key)

    for sel in curso_sels:
        try:
            _etapa, _num, _titulo, grupos_c = _resolver_grupos_curso(sel)
            datos_map = {g: datos_all[g] for g in grupos_c if g in datos_all}
            missing = [g for g in grupos_c if g not in datos_map]
            if missing:
                for g in missing:
                    datos_map[g] = datos_sesion_evaluacion_grupo(g)
                    datos_all[g] = datos_map[g]
            materias = build_informe_curso_materias(sel, datos_map=datos_map)
            ranking = build_informe_curso_ranking(sel, datos_map=datos_map)
            competencias = build_informe_curso_competencias(sel, datos_map=datos_map)
            decision = build_informe_curso_decision(sel, datos_map=datos_map)
            alumnos = build_informe_curso_alumnos(sel, datos_map=datos_map)
            for vista, payload in (
                ("materias", materias),
                ("ranking", ranking),
                ("competencias", competencias),
                ("decision", decision),
                ("alumnos", alumnos),
            ):
                save_informe_cache(ambito="curso", sel=sel, vista=vista, payload=payload)
                n_ok += 1
            save_informe_cache(
                ambito="curso",
                sel=sel,
                vista="completo",
                payload={
                    "grupo": _titulo,
                    "ambito_label": "Curso",
                    "sel": (sel or "").strip().lower(),
                    "curso_escolar": _school_year_short(),
                    "grupos": grupos_c,
                    "materias": materias,
                    "ranking": ranking,
                    "competencias": competencias,
                    "decision": decision,
                    "alumnos": alumnos,
                },
            )
            n_ok += 1
        except Exception as exc:
            errors.append(f"curso {sel}: {exc}")

    for sel in ("eso", "bachillerato"):
        try:
            payload = build_informe_etapa_suspensos_alumno(sel, datos_map=datos_all)
            save_informe_cache(
                ambito="etapa", sel=sel, vista="suspensos_alumno", payload=payload
            )
            n_ok += 1
            save_informe_cache(
                ambito="etapa", sel=sel, vista="suspensos_grupo", payload=payload
            )
            n_ok += 1
        except Exception as exc:
            errors.append(f"etapa {sel}: {exc}")

    return {
        "n_ok": n_ok,
        "errors": errors,
        "calculated_at": latest_informes_cache_at(),
    }
