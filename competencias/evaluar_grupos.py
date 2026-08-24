"""Agrupación de grupos y materias para la pantalla Calificar."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ausencias.db import list_schedule_slots
from db.connection import get_db
from db.enrolled_subject_catalog import (
    bach_competencias_canonical_label,
    bach_competencias_curso_override,
    competencias_materia_group_key,
    ensure_subject_catalog_schema,
    list_catalog_for_export,
    resolve_catalog_stage,
)
from db.enrolled_subjects import (
    CARACTERISTICA_MATERIA_PENDIENTE,
    ensure_enrolled_subjects_schema,
)
from db.groups import ensure_groups_schema, get_group_curso, list_groups_with_course
from utils.enums import ROLE_INVITADO, ROLE_ORIENTADOR, ROLES_ADMINISTRATIVOS
from utils.group_stage import extract_course_num, stage_of
from utils.text import normalize_for_sort


def user_ve_todo_calificar(user: dict | None) -> bool:
    """Equipo directivo / administración / invitado: todos los grupos y materias."""
    if not user:
        return False
    role = (user.get("role") or "").strip().lower()
    return role in ROLES_ADMINISTRATIVOS or role == ROLE_INVITADO


def user_ve_todas_evaluaciones(user: dict | None) -> bool:
    """Directivos, orientación e invitado ven todos los grupos en Evaluaciones."""
    if not user:
        return False
    role = (user.get("role") or "").strip().lower()
    return role in ROLES_ADMINISTRATIVOS or role in {ROLE_ORIENTADOR, ROLE_INVITADO}


def puede_ver_evaluacion_grupo(user: dict | None, grupo: str) -> bool:
    if user_ve_todas_evaluaciones(user):
        return True
    key = (grupo or "").strip().casefold()
    if not key:
        return False
    return key in docencia_por_grupo(user)


def _tokens_texto_asignatura(raw: str | None) -> set[str]:
    text = (raw or "").strip()
    if not text:
        return set()
    out = {text.casefold(), normalize_for_sort(text)}
    key = competencias_materia_group_key(text)
    if key:
        out.add(key)
    return {t for t in out if t}


def _mapa_abrev_catalogo() -> dict[str, set[str]]:
    """Abreviatura (casefold) → claves de materia del catálogo."""
    out: dict[str, set[str]] = {}
    ensure_subject_catalog_schema()
    for row in list_catalog_for_export():
        abrev = (row.get("materia_abrev") or "").strip()
        if not abrev:
            continue
        bucket = out.setdefault(abrev.casefold(), set())
        bucket |= _tokens_texto_asignatura(abrev)
        bucket |= _tokens_texto_asignatura(row.get("materia"))
    return out


def _tokens_horario_asignatura(
    raw: str | None, abrev_map: dict[str, set[str]]
) -> set[str]:
    tokens = _tokens_texto_asignatura(raw)
    extra: set[str] = set()
    for tok in list(tokens):
        extra |= abrev_map.get(tok, set())
    return tokens | extra


def docencia_por_grupo(user: dict | None) -> dict[str, set[str]]:
    """Grupo (casefold) → tokens de asignatura según horas CLASS del profesor."""
    if not user or user.get("id") is None:
        return {}
    try:
        teacher_id = int(user["id"])
    except (TypeError, ValueError):
        return {}
    abrev_map = _mapa_abrev_catalogo()
    out: dict[str, set[str]] = {}
    for slot in list_schedule_slots(teacher_id=teacher_id):
        kind = str(slot.get("slot_type") or slot.get("type") or "").strip().upper()
        if kind != "CLASS":
            continue
        grupo = (slot.get("group") or "").strip()
        if not grupo:
            continue
        tokens = out.setdefault(grupo.casefold(), set())
        tokens |= _tokens_horario_asignatura(slot.get("subject"), abrev_map)
    return out


def profesor_imparte_grupo(user: dict | None, grupo: str) -> bool:
    if user_ve_todo_calificar(user):
        return True
    key = (grupo or "").strip().casefold()
    if not key:
        return False
    return key in docencia_por_grupo(user)


def _tokens_materia_evaluar(m: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for raw in (m.get("materia_key"), m.get("materia_abrev"), m.get("materia")):
        out |= _tokens_texto_asignatura(raw if isinstance(raw, str) else str(raw or ""))
    return out


def profesor_imparte_materia(
    user: dict | None,
    grupo: str,
    materia: dict[str, Any],
    *,
    docencia: dict[str, set[str]] | None = None,
) -> bool:
    if user_ve_todo_calificar(user):
        return True
    mapa = docencia if docencia is not None else docencia_por_grupo(user)
    tokens_grupo = mapa.get((grupo or "").strip().casefold()) or set()
    if not tokens_grupo:
        return False
    return bool(tokens_grupo & _tokens_materia_evaluar(materia))


def profesor_puede_calificar_materia(
    user: dict | None,
    grupo: str,
    *,
    materia_key: str,
    curso_asignatura: int | None = None,
    pendiente: bool | None = None,
    sesion: str | None = None,
) -> bool:
    if user_ve_todo_calificar(user):
        return True
    if not profesor_imparte_grupo(user, grupo):
        return False
    want = (materia_key or "").strip()
    for m in materias_para_evaluar_grupo(grupo, sesion=sesion, user=user):
        if (m.get("materia_key") or "").strip() != want:
            continue
        if curso_asignatura is not None and m.get("curso_asignatura") is not None:
            try:
                if int(m["curso_asignatura"]) != int(curso_asignatura):
                    continue
            except (TypeError, ValueError):
                continue
        if pendiente is not None and bool(m.get("es_pendiente")) != bool(pendiente):
            continue
        return True
    return False


def grupos_para_evaluar(
    *,
    user: dict | None = None,
    ver_todos: bool | None = None,
) -> dict[str, list[str]]:
    """Tres columnas: 1º–2º ESO, 3º–4º ESO, Bachillerato."""
    ensure_groups_schema()
    eso_12: list[str] = []
    eso_34: list[str] = []
    bach: list[str] = []

    for g in list_groups_with_course():
        name = (g.get("name") or "").strip()
        if not name:
            continue
        curso = (g.get("curso") or "").strip() or None
        stage = stage_of(grupo=name, curso=curso)
        if not stage:
            continue
        num = extract_course_num(grupo=name, curso=curso, stage=stage)
        if stage == "eso" and num in (1, 2):
            eso_12.append(name)
        elif stage == "eso" and num in (3, 4):
            eso_34.append(name)
        elif stage == "bachillerato":
            bach.append(name)

    for lst in (eso_12, eso_34, bach):
        lst.sort(key=normalize_for_sort)

    cols = {
        "eso_12": eso_12,
        "eso_34": eso_34,
        "bach": bach,
    }
    show_all = (
        ver_todos
        if ver_todos is not None
        else (user is None or user_ve_todo_calificar(user))
    )
    if show_all:
        return cols
    allowed = set(docencia_por_grupo(user))
    return {
        key: [g for g in names if g.casefold() in allowed]
        for key, names in cols.items()
    }


SESIONES_BACH: tuple[str, str] = ("ordinaria", "extraordinaria")
SESION_LABELS: dict[str, str] = {
    "ordinaria": "Ordinaria",
    "extraordinaria": "Extraordinaria",
}


def etapa_del_grupo(grupo: str) -> str | None:
    curso = get_group_curso(grupo)
    return stage_of(grupo=grupo, curso=curso)


def normalizar_sesion_bach(sesion: str | None) -> str | None:
    key = (sesion or "").strip().lower()
    if key in SESIONES_BACH:
        return key
    return None


def estilo_grupo_evaluar(
    grupo: str,
    *,
    evaluada: bool = False,
    pendiente: bool = False,
    stage: str | None = None,
    num: int | None = None,
) -> str:
    """Clase de color del botón según la columna del grupo.

    Materias del curso actual: color de etapa. Pendientes de cursos
    anteriores: naranja. Ya evaluadas: tono suave.
    """
    if stage is None:
        curso = get_group_curso(grupo)
        stage = stage_of(grupo=grupo, curso=curso)
        num = (
            extract_course_num(grupo=grupo, curso=curso, stage=stage)
            if stage
            else None
        )
    if pendiente:
        if evaluada:
            return "bg-orange-200 text-gray-600 hover:bg-orange-300"
        return "bg-orange-600 text-white hover:bg-orange-700"
    if evaluada:
        if stage == "eso" and num in (1, 2):
            return "bg-teal-200 text-gray-600 hover:bg-teal-300"
        if stage == "eso" and num in (3, 4):
            return "bg-cyan-200 text-gray-600 hover:bg-cyan-300"
        return "bg-violet-200 text-gray-600 hover:bg-violet-300"
    if stage == "eso" and num in (1, 2):
        return "bg-teal-600 text-white hover:bg-teal-700"
    if stage == "eso" and num in (3, 4):
        return "bg-cyan-600 text-white hover:bg-cyan-700"
    if stage == "bachillerato":
        return "bg-violet-600 text-white hover:bg-violet-700"
    return "bg-teal-600 text-white hover:bg-teal-700"


def _paleta_grupo(grupo: str) -> dict[tuple[bool, bool], str]:
    """(pendiente, evaluada) → clase CSS. Una sola lectura del curso del grupo."""
    curso = get_group_curso(grupo)
    stage = stage_of(grupo=grupo, curso=curso)
    num = (
        extract_course_num(grupo=grupo, curso=curso, stage=stage) if stage else None
    )
    return {
        (False, False): estilo_grupo_evaluar(
            grupo, evaluada=False, pendiente=False, stage=stage, num=num
        ),
        (False, True): estilo_grupo_evaluar(
            grupo, evaluada=True, pendiente=False, stage=stage, num=num
        ),
        (True, False): estilo_grupo_evaluar(
            grupo, evaluada=False, pendiente=True, stage=stage, num=num
        ),
        (True, True): estilo_grupo_evaluar(
            grupo, evaluada=True, pendiente=True, stage=stage, num=num
        ),
    }


def _filas_materias_grupo(*, nombre: str, import_id: int) -> list[dict[str, Any]]:
    """Materias actuales y pendientes del grupo en una sola consulta."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT
                    TRIM(es.materia) AS materia,
                    TRIM(es.materia_abrev) AS materia_abrev,
                    TRIM(es.alumno) AS alumno,
                    c.materia AS catalog_materia,
                    c.curso_asignatura,
                    c.etapa,
                    c.estudio,
                    (TRIM(COALESCE(es.caracteristicas, '')) = %s) AS es_pendiente
                FROM enrolled_subjects es
                LEFT JOIN enrolled_subject_catalog c
                  ON TRIM(c.materia_abrev) = TRIM(es.materia_abrev)
                LEFT JOIN students s
                  ON LOWER(TRIM(s.alumno)) = LOWER(TRIM(es.alumno))
                WHERE es.import_id = %s
                  AND TRIM(COALESCE(es.materia, '')) <> ''
                  AND (
                    LOWER(TRIM(es.nombre_grupo)) = LOWER(TRIM(%s))
                    OR LOWER(TRIM(COALESCE(s.grupo, ''))) = LOWER(TRIM(%s))
                  )
                ORDER BY TRIM(es.materia)
                """,
                (
                    CARACTERISTICA_MATERIA_PENDIENTE,
                    import_id,
                    nombre,
                    nombre,
                ),
            )
            return [dict(r) for r in cur.fetchall()]


def _al(nombre: str) -> str:
    return " ".join((nombre or "").split()).casefold()


def _agrupar_materias_filas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int | None, bool], dict[str, Any]] = {}
    for row in rows:
        materia = (row.get("catalog_materia") or row.get("materia") or "").strip()
        if not materia:
            continue
        key = competencias_materia_group_key(materia)
        if not key:
            key = materia.casefold()
        try:
            curso = (
                int(row["curso_asignatura"])
                if row.get("curso_asignatura") is not None
                else None
            )
        except (TypeError, ValueError):
            curso = None
        etapa = resolve_catalog_stage(
            etapa=row.get("etapa"),
            estudio=row.get("estudio"),
            materia_abrev=row.get("materia_abrev"),
            materia=materia,
        )
        if etapa == "bach":
            curso_override = bach_competencias_curso_override(key)
            if curso_override is not None:
                curso = curso_override
        if etapa == "bach" and curso:
            materia = bach_competencias_canonical_label(key, curso, materia)
        es_pendiente = bool(row.get("es_pendiente"))
        alumno = _al(str(row.get("alumno") or ""))

        gkey = (key, curso, es_pendiente)
        existing = grouped.get(gkey)
        if existing is None:
            grouped[gkey] = {
                "materia": materia,
                "materia_key": key,
                "curso_asignatura": curso,
                "etapa": etapa,
                "materia_abrev": (row.get("materia_abrev") or "").strip() or None,
                "es_pendiente": es_pendiente,
                "alumnos": {alumno} if alumno else set(),
            }
            continue
        if len(materia) > len(existing["materia"] or ""):
            existing["materia"] = materia
        if etapa and not existing.get("etapa"):
            existing["etapa"] = etapa
        if alumno:
            existing["alumnos"].add(alumno)

    out = list(grouped.values())
    out.sort(
        key=lambda m: (
            1 if m.get("es_pendiente") else 0,
            normalize_for_sort(m.get("materia") or ""),
        )
    )
    return out


def _triple_materia(m: dict[str, Any]) -> tuple[str, int, str] | None:
    etapa = (m.get("etapa") or "").strip().lower()
    key = (m.get("materia_key") or "").strip()
    try:
        curso_n = (
            int(m["curso_asignatura"])
            if m.get("curso_asignatura") is not None
            else None
        )
    except (TypeError, ValueError):
        curso_n = None
    if curso_n is None or not etapa or not key:
        return None
    return (etapa, curso_n, key)


def _lookup_maps(maps: dict, m: dict[str, Any]):
    t = _triple_materia(m)
    if not t:
        return None
    if t in maps:
        return maps[t]
    etapa, curso, key = t
    fam = competencias_materia_group_key(key) or key
    return maps.get((etapa, curso, fam))


def _comp_completa(m: dict[str, Any], notas_comp: dict, criterios: dict) -> bool:
    alumnos = m.get("alumnos") or set()
    if not alumnos:
        return False
    needed = _lookup_maps(criterios, m)
    if not needed:
        return False
    por_al = _lookup_maps(notas_comp, m) or {}
    for al in alumnos:
        have = por_al.get(al) or set()
        if needed - have:
            return False
    return True


def _acta_completa(m: dict[str, Any], notas_acta: dict) -> bool:
    alumnos = m.get("alumnos") or set()
    if not alumnos:
        return False
    have = _lookup_maps(notas_acta, m) or set()
    return alumnos <= have


def _marcar_evaluadas(
    materias: list[dict[str, Any]],
    *,
    paleta: dict[tuple[bool, bool], str],
    notas_comp: dict,
    notas_acta: dict,
    criterios: dict,
    alumnos_subset: dict[int, set[str]] | None = None,
) -> None:
    for i, m in enumerate(materias):
        pendiente = bool(m.get("es_pendiente"))
        alumnos = m.get("alumnos") or set()
        if alumnos_subset is not None:
            alumnos = set(alumnos_subset.get(i, alumnos))
            m["_alumnos_eval"] = alumnos
        if not alumnos:
            m["evaluada"] = False
            m["tiene_nota_comp"] = False
            m["tiene_nota_acta"] = False
            m["btn_class"] = paleta[(pendiente, False)]
            m["btn_class_comp"] = paleta[(pendiente, False)]
            m["btn_class_acta"] = paleta[(pendiente, False)]
            continue
        m_check = {**m, "alumnos": alumnos}
        tiene_comp = _comp_completa(m_check, notas_comp, criterios)
        tiene_acta = _acta_completa(m_check, notas_acta)
        m["evaluada"] = tiene_comp
        m["tiene_nota_comp"] = tiene_comp
        m["tiene_nota_acta"] = tiene_acta
        m["es_pendiente"] = pendiente
        m["btn_class"] = paleta[(pendiente, tiene_comp and tiene_acta)]
        m["btn_class_comp"] = paleta[(pendiente, tiene_comp)]
        m["btn_class_acta"] = paleta[(pendiente, tiene_acta)]


def _alumnos_extraordinaria_materia(
    m: dict[str, Any],
    snapshot: dict[tuple[str, int, str], dict[str, Decimal | None]],
) -> set[str]:
    from db.competencias_bach_ordinaria import nota_snapshot_ordinaria

    t = _triple_materia(m)
    if not t:
        return set()
    etapa, curso, key = t
    out: set[str] = set()
    for al in m.get("alumnos") or set():
        nota_ord = nota_snapshot_ordinaria(
            snapshot,
            etapa=etapa,
            curso=curso,
            materia_key=key,
            al_norm=al,
        )
        if nota_ord is None or nota_ord < Decimal("5"):
            out.add(al)
    return out


def _cohorte_extraordinaria_bach(
    agrupadas: list[dict[str, Any]],
    snapshot: dict[tuple[str, int, str], dict[str, Decimal | None]],
) -> set[str]:
    """Alumnos que no aprobaron alguna materia (actual o pendiente) en la ordinaria."""
    from db.competencias_bach_ordinaria import nota_snapshot_ordinaria

    cohort: set[str] = set()
    for m in agrupadas:
        t = _triple_materia(m)
        if not t:
            continue
        etapa, curso, key = t
        for al in m.get("alumnos") or set():
            nota_ord = nota_snapshot_ordinaria(
                snapshot,
                etapa=etapa,
                curso=curso,
                materia_key=key,
                al_norm=al,
            )
            if nota_ord is None or nota_ord < Decimal("5"):
                cohort.add(al)
    return cohort


def _filtrar_materias_extraordinaria(
    materias: list[dict[str, Any]],
    snapshot: dict[tuple[str, int, str], dict[str, Decimal | None]],
) -> tuple[list[dict[str, Any]], dict[int, set[str]]]:
    """Materias con alumnos suspendidos en ordinaria y mapa índice → alumnos a evaluar."""
    filtradas: list[dict[str, Any]] = []
    alumnos_por_indice: dict[int, set[str]] = {}
    for m in materias:
        al_extra = _alumnos_extraordinaria_materia(m, snapshot)
        if not al_extra:
            continue
        alumnos_por_indice[len(filtradas)] = al_extra
        filtradas.append(m)
    return filtradas, alumnos_por_indice


def materia_aprobada_ordinaria_alumno(
    m: dict[str, Any],
    al_norm: str,
    snapshot: dict[tuple[str, int, str], dict[str, Decimal | None]],
) -> bool:
    from db.competencias_bach_ordinaria import aprobado_en_ordinaria, nota_snapshot_ordinaria

    t = _triple_materia(m)
    if not t:
        return False
    etapa, curso, key = t
    return aprobado_en_ordinaria(
        nota_snapshot_ordinaria(
            snapshot,
            etapa=etapa,
            curso=curso,
            materia_key=key,
            al_norm=al_norm,
        )
    )


def materia_label_para_evaluar(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> str:
    """Nombre de materia sin reconstruir el listado del grupo."""
    key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    etapa_v = (etapa or "").strip().lower()
    curso = int(curso_asignatura)
    best = ""
    ensure_subject_catalog_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT materia
                FROM enrolled_subject_catalog
                WHERE curso_asignatura = %s
                """,
                (curso,),
            )
            for r in cur.fetchall():
                mat = (r.get("materia") or "").strip()
                rk = competencias_materia_group_key(mat) or mat.casefold()
                if rk == key and len(mat) > len(best):
                    best = mat
    if etapa_v == "bach":
        return bach_competencias_canonical_label(key, curso, best) or best or key
    return best or key


def materias_para_evaluar_grupo(
    grupo: str,
    *,
    sesion: str | None = None,
    user: dict | None = None,
) -> list[dict[str, Any]]:
    """Materias del curso actual y pendientes de cursos anteriores."""
    from db.competencias_evaluacion import mapas_notas_grupo
    from db.competencias_materia_criterios import map_criterios_codes
    from db.enrolled_subjects import _latest_import_id

    nombre = (grupo or "").strip()
    if not nombre:
        return []

    sesion_v = (sesion or "").strip().lower()
    es_extra = sesion_v == "extraordinaria"

    ensure_enrolled_subjects_schema()
    ensure_subject_catalog_schema()
    import_id = _latest_import_id()
    if not import_id:
        return []

    agrupadas = _agrupar_materias_filas(
        _filas_materias_grupo(nombre=nombre, import_id=import_id)
    )
    actuales: list[dict[str, Any]] = []
    pendientes: list[dict[str, Any]] = []
    actuales_keys: set[tuple[Any, Any]] = set()
    for m in agrupadas:
        if m.get("es_pendiente"):
            pendientes.append(m)
        else:
            actuales.append(m)
            actuales_keys.add((m.get("materia_key"), m.get("curso_asignatura")))
    pendientes = [
        m
        for m in pendientes
        if (m.get("materia_key"), m.get("curso_asignatura")) not in actuales_keys
    ]

    snapshot: dict[tuple[str, int, str], dict[str, Decimal | None]] = {}
    alumnos_extra_por_materia: dict[int, set[str]] = {}
    if es_extra:
        from db.competencias_bach_ordinaria import (
            ensure_snapshot_ordinaria_grupo,
            mapa_snapshot_ordinaria,
        )

        ensure_snapshot_ordinaria_grupo(nombre)
        snapshot = mapa_snapshot_ordinaria(nombre)
        actuales, alumnos_extra_por_materia = _filtrar_materias_extraordinaria(
            actuales, snapshot
        )
        pendientes, alumnos_extra_por_pendiente = _filtrar_materias_extraordinaria(
            pendientes, snapshot
        )

    notas_comp, notas_acta = mapas_notas_grupo(nombre, sesion=sesion_v if es_extra else None)
    criterios = map_criterios_codes()
    paleta = _paleta_grupo(nombre)
    _marcar_evaluadas(
        actuales,
        paleta=paleta,
        notas_comp=notas_comp,
        notas_acta=notas_acta,
        criterios=criterios,
        alumnos_subset=alumnos_extra_por_materia if es_extra else None,
    )
    _marcar_evaluadas(
        pendientes,
        paleta=paleta,
        notas_comp=notas_comp,
        notas_acta=notas_acta,
        criterios=criterios,
        alumnos_subset=alumnos_extra_por_pendiente if es_extra else None,
    )
    out = actuales + pendientes
    if user is not None and not user_ve_todo_calificar(user):
        docencia = docencia_por_grupo(user)
        out = [
            m
            for m in out
            if profesor_imparte_materia(user, nombre, m, docencia=docencia)
        ]
    return out


def list_pendientes_aviso_calificar(
    user: dict | None,
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Grupos/sesiones del profesor con notas pendientes, 1–2 días antes de la sesión."""
    from urllib.parse import quote

    from db.competencias_fechas_sesion import (
        DIAS_AVISO_CALIFICACIONES,
        SESION_ESO,
        SESION_EXT,
        SESION_ORD,
        en_ventana_aviso_calificaciones,
        format_fecha_sesion,
        hoy_madrid,
        map_fechas_sesion,
    )

    if not user or user.get("id") is None:
        return []
    dia = today or hoy_madrid()
    docencia = docencia_por_grupo(user)
    if not docencia:
        return []

    fechas = map_fechas_sesion()
    pendientes: list[dict[str, Any]] = []
    for g in list_groups_with_course():
        nombre = (g.get("name") or "").strip()
        if not nombre:
            continue
        gkey = nombre.casefold()
        tokens_grupo = docencia.get(gkey)
        if not tokens_grupo:
            continue
        curso = (g.get("curso") or "").strip() or None
        stage = stage_of(grupo=nombre, curso=curso)
        if stage == "bachillerato":
            sesiones: tuple[tuple[str | None, str], ...] = (
                ("ordinaria", SESION_ORD),
                ("extraordinaria", SESION_EXT),
            )
        else:
            sesiones = ((None, SESION_ESO),)
        for sesion_key, fecha_key in sesiones:
            fecha = fechas.get((nombre, fecha_key)) or fechas.get((gkey, fecha_key))
            if not en_ventana_aviso_calificaciones(fecha, today=dia):
                continue
            materias = [
                m
                for m in materias_para_evaluar_grupo(
                    nombre, sesion=sesion_key
                )
                if tokens_grupo & _tokens_materia_evaluar(m)
            ]
            faltan: list[str] = []
            for m in materias:
                if m.get("tiene_nota_comp") and m.get("tiene_nota_acta"):
                    continue
                label = (m.get("materia") or m.get("materia_key") or "").strip()
                if not label:
                    continue
                if m.get("es_pendiente"):
                    label = f"{label} (pendiente)"
                faltan.append(label)
            if not faltan:
                continue
            href = f"/competencias/evaluar/{quote(nombre)}"
            if sesion_key:
                href += f"?sesion={sesion_key}"
            aviso_id = f"{gkey}_{sesion_key or 'eso'}"
            pendientes.append(
                {
                    "aviso_id": aviso_id,
                    "grupo": nombre,
                    "sesion_key": sesion_key,
                    "sesion_label": SESION_LABELS.get(sesion_key) if sesion_key else None,
                    "fecha_sesion": fecha,
                    "fecha_sesion_display": format_fecha_sesion(fecha),
                    "fecha_aviso": fecha - timedelta(days=DIAS_AVISO_CALIFICACIONES),
                    "materias": faltan,
                    "href": href,
                }
            )
    pendientes.sort(
        key=lambda item: (
            item.get("fecha_sesion") or dia,
            normalize_for_sort(item.get("grupo") or ""),
            item.get("sesion_key") or "",
        )
    )
    return pendientes


def _fecha_display(value: object) -> str:
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}/{text[5:7]}/{text[:4]}"
    return text


def _alumnos_sesion(grupo: str) -> list[dict[str, str]]:
    nombre = (grupo or "").strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT alumno, fecha_nacimiento
                FROM students
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                """,
                (nombre,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    out = [
        {
            "alumno": str(r.get("alumno") or "").strip(),
            "fecha_nacimiento": _fecha_display(r.get("fecha_nacimiento")),
        }
        for r in rows
        if str(r.get("alumno") or "").strip()
    ]
    out.sort(key=lambda a: normalize_for_sort(a["alumno"]))
    return out


def _nota_acta_decimal(
    m: dict[str, Any],
    al_norm: str,
    notas: dict[tuple[str, int, str], dict[str, Any]],
) -> Decimal | None:
    t = _triple_materia(m)
    if not t:
        return None
    por_al = notas.get(t)
    if por_al is None:
        etapa, curso, key = t
        fam = competencias_materia_group_key(key) or key
        por_al = notas.get((etapa, curso, fam))
    if not por_al:
        return None
    nota = por_al.get(al_norm)
    if nota is None:
        return None
    return Decimal(str(nota))


def _ppd_materia(
    m: dict[str, Any],
    *,
    sesion: str | None,
    cache: dict[tuple[str, int, str, bool, str], dict[str, Decimal]],
) -> dict[str, Decimal]:
    t = _triple_materia(m)
    if not t:
        return {}
    etapa, curso, key = t
    pend = bool(m.get("es_pendiente"))
    ses = (sesion or "").strip().lower()
    ck = (etapa, curso, key, pend, ses)
    if ck not in cache:
        from db.competencias_materia_variables import contexto_ppd_phoras_materia

        cache[ck] = contexto_ppd_phoras_materia(
            etapa=etapa,
            curso_asignatura=curso,
            materia_key=key,
            sesion=ses or None,
            pendiente=pend,
        )["ppd_map"]
    return cache[ck]


def _nota_comp_decimal(
    m: dict[str, Any],
    al_norm: str,
    notas: dict[tuple[str, int, str], dict[str, dict[str, Decimal]]],
    *,
    sesion: str | None,
    ppd_cache: dict[tuple[str, int, str, bool, str], dict[str, Decimal]],
) -> Decimal | None:
    from db.competencias_evaluacion import compute_nota_comp

    por_al = _lookup_maps(notas, m) or {}
    por_crit = por_al.get(al_norm) or {}
    ppd_map = _ppd_materia(m, sesion=sesion, cache=ppd_cache)
    if not por_crit or not ppd_map:
        return None
    return compute_nota_comp(por_crit, ppd_map)


def _es_suspensa(nota: Decimal | None) -> bool:
    if nota is None:
        return True
    return nota < 5


def _media_notas_2d(valores: list[Decimal | None]) -> str:
    """Media aritmética simple; solo notas presentes. Formato 2 decimales."""
    from db.competencias_calculo_config import format_nota_cc_2d_es

    nums = [v for v in valores if v is not None]
    if not nums:
        return ""
    return format_nota_cc_2d_es(sum(nums, Decimal("0")) / Decimal(len(nums)))


def _parse_nota_es(raw: object) -> Decimal | None:
    text = str(raw or "").strip().replace(",", ".")
    if not text or text == "—":
        return None
    try:
        return Decimal(text)
    except Exception:
        return None


def _media_competencias_filas(filas: list[dict[str, Any]]) -> str:
    vals: list[Decimal | None] = []
    for c in filas:
        if c.get("editada_sesion"):
            vals.append(_parse_nota_es(c.get("nota")))
            continue
        v = _parse_nota_es(c.get("nota_2d"))
        if v is None:
            v = _parse_nota_es(c.get("nota"))
        vals.append(v)
    return _media_notas_2d(vals)


def _decision_bach(
    curso_num: int | None,
    notas: list[Decimal | None],
    *,
    sesion: str | None = None,
) -> tuple[str | None, bool | None]:
    """1.º Bach: PROMOCIONA con ≤2 suspensas. 2.º Bach: TITULA según convocatoria."""
    if curso_num not in (1, 2) or not notas:
        return None, None
    n_suspensas = sum(1 for n in notas if _es_suspensa(n))
    if curso_num == 1:
        ok = n_suspensas <= 2
        return ("PROMOCIONA" if ok else "NO PROMOCIONA"), ok
    max_suspensas = 1 if sesion == "extraordinaria" else 0
    ok = n_suspensas <= max_suspensas
    return ("TITULA" if ok else "NO TITULA"), ok


def _item_materia_sesion(
    m: dict[str, Any],
    al_norm: str,
    notas_acta: dict,
    notas_comp: dict,
    *,
    sesion: str | None,
    overrides: dict[tuple[str, str], int],
    snapshot: dict[tuple[str, int, str], dict[str, Decimal | None]] | None = None,
    es_extra_sesion: bool = False,
    notas_acta_extra: dict | None = None,
    notas_comp_extra: dict | None = None,
) -> dict[str, Any]:
    from db.competencias_bach_ordinaria import nota_snapshot_ordinaria
    from db.competencias_calculo_config import format_nota_cc_2d_es
    from db.competencias_evaluacion import acta_es_cualitativa, format_nota_acta_es
    from db.competencias_sesion_notas import SCOPE_MATERIA, materia_scope_key, override_o_none

    t = _triple_materia(m)
    de_ordinaria = bool(
        es_extra_sesion
        and snapshot is not None
        and materia_aprobada_ordinaria_alumno(m, al_norm, snapshot)
    )
    if de_ordinaria and t and snapshot is not None:
        etapa, curso, key = t
        nota_val = nota_snapshot_ordinaria(
            snapshot,
            etapa=etapa,
            curso=curso,
            materia_key=key,
            al_norm=al_norm,
        )
        nota_comp_val = _nota_acta_decimal(m, al_norm, notas_comp)
    elif es_extra_sesion:
        nota_val = _nota_acta_decimal(m, al_norm, notas_acta_extra or {})
        nota_comp_val = _nota_acta_decimal(m, al_norm, notas_comp_extra or {})
    else:
        nota_val = _nota_acta_decimal(m, al_norm, notas_acta)
        nota_comp_val = _nota_acta_decimal(m, al_norm, notas_comp)
    scope_key = ""
    editada = False
    if t and not de_ordinaria:
        etapa, curso, key = t
        scope_key = materia_scope_key(etapa=etapa, curso=curso, materia_key=key)
        ov = override_o_none(overrides, scope=SCOPE_MATERIA, scope_key=scope_key)
        if ov is not None:
            nota_val = Decimal(str(ov))
            editada = True
    return {
        "materia": m.get("materia") or "",
        "es_pendiente": bool(m.get("es_pendiente")),
        "etapa": (m.get("etapa") or "").strip().lower(),
        "curso_asignatura": m.get("curso_asignatura"),
        "materia_key": (m.get("materia_key") or "").strip(),
        "scope_key": scope_key,
        "nota_acta": format_nota_acta_es(
            nota_val,
            cualitativa=acta_es_cualitativa(m.get("etapa")),
        )
        if nota_val is not None
        else "",
        "nota_comp": format_nota_cc_2d_es(nota_comp_val),
        "editada_sesion": editada,
        "de_ordinaria": de_ordinaria,
        "_nota": nota_val,
        "_nota_comp": nota_comp_val,
    }


def _aplicar_overrides_competencias(
    filas: list[dict[str, str]],
    overrides: dict[tuple[str, str], int],
) -> list[dict[str, str]]:
    from db.competencias_evaluacion import format_nota_acta_es
    from db.competencias_sesion_notas import SCOPE_COMPETENCIA, override_o_none

    out: list[dict[str, str]] = []
    for fila in filas:
        copia = dict(fila)
        abrev = (copia.get("abreviatura") or "").strip()
        ov = override_o_none(overrides, scope=SCOPE_COMPETENCIA, scope_key=abrev)
        if ov is not None:
            copia["nota"] = format_nota_acta_es(Decimal(str(ov)))
            copia["editada_sesion"] = True
        else:
            copia["editada_sesion"] = False
        out.append(copia)
    return out


def _notas_decision_alumno(
    *,
    agrupadas: list[dict[str, Any]],
    al_norm: str,
    notas_acta: dict,
    notas_comp: dict,
    sesion: str | None,
    overrides: dict[tuple[str, str], int],
    snapshot: dict | None = None,
    es_extra_sesion: bool = False,
    notas_acta_extra: dict | None = None,
    notas_comp_extra: dict | None = None,
) -> list[Decimal | None]:
    curso: list[dict[str, Any]] = []
    pendientes: list[dict[str, Any]] = []
    actuales_keys: set[tuple[Any, Any]] = set()
    for m in agrupadas:
        if al_norm not in (m.get("alumnos") or set()):
            continue
        item = _item_materia_sesion(
            m,
            al_norm,
            notas_acta,
            notas_comp,
            sesion=sesion,
            overrides=overrides,
            snapshot=snapshot,
            es_extra_sesion=es_extra_sesion,
            notas_acta_extra=notas_acta_extra,
            notas_comp_extra=notas_comp_extra,
        )
        if item["es_pendiente"]:
            pendientes.append({**item, "_key": (m.get("materia_key"), m.get("curso_asignatura"))})
        else:
            actuales_keys.add((m.get("materia_key"), m.get("curso_asignatura")))
            curso.append(item)
    pendientes_visibles = [
        p for p in pendientes if p["_key"] not in actuales_keys
    ]
    return [m["_nota"] for m in curso] + [p["_nota"] for p in pendientes_visibles]


def guardar_nota_sesion_alumno(
    *,
    grupo: str,
    sesion: str | None,
    alumno: str,
    scope: str,
    scope_key: str,
    nota_raw: object,
    updated_by: int | None = None,
) -> dict[str, Any]:
    """Persiste override de sesión y devuelve estado actualizado del alumno."""
    from db.competencias_evaluacion import (
        acta_es_cualitativa,
        format_nota_acta_es,
        mapa_notas_acta_valores,
        mapa_notas_comp_valores,
    )
    from db.competencias_sesion_notas import (
        SCOPE_COMPETENCIA,
        SCOPE_MATERIA,
        guardar_override_sesion,
        mapa_overrides_sesion,
        parse_nota_sesion_entera,
    )
    from db.enrolled_subjects import _latest_import_id

    nombre = (grupo or "").strip()
    al_canon = str(alumno or "").strip()
    al_norm = _al(al_canon)
    if not nombre or not al_canon:
        raise ValueError("Alumno no indicado")

    scope_v = (scope or "").strip().lower()
    skey = (scope_key or "").strip()
    if scope_v not in (SCOPE_MATERIA, SCOPE_COMPETENCIA) or not skey:
        raise ValueError("Tipo de nota no válido")

    cualitativa = False
    if scope_v == SCOPE_MATERIA:
        parts = skey.split("|", 2)
        if len(parts) == 3:
            cualitativa = acta_es_cualitativa(parts[0])
    nota_nueva = parse_nota_sesion_entera(nota_raw, cualitativa=cualitativa)
    es_extra = (sesion or "").strip().lower() == "extraordinaria"

    ensure_enrolled_subjects_schema()
    ensure_subject_catalog_schema()
    import_id = _latest_import_id()
    agrupadas = (
        _agrupar_materias_filas(_filas_materias_grupo(nombre=nombre, import_id=import_id))
        if import_id
        else []
    )
    notas_acta = mapa_notas_acta_valores(nombre)
    notas_comp = mapa_notas_comp_valores(nombre)
    notas_acta_extra: dict = {}
    notas_comp_extra: dict = {}

    original_str = ""
    if scope_v == SCOPE_MATERIA:
        parts = skey.split("|", 2)
        if len(parts) != 3:
            raise ValueError("Materia no válida")
        etapa_p, curso_p, key_p = parts[0], int(parts[1]), parts[2]
        meta = next(
            (
                m
                for m in agrupadas
                if (m.get("etapa") or "").strip().lower() == etapa_p
                and int(m.get("curso_asignatura") or 0) == curso_p
                and (m.get("materia_key") or "").strip() == key_p
            ),
            None,
        )
        if meta is None:
            raise ValueError("Materia no encontrada")
        if al_norm not in (meta.get("alumnos") or set()):
            raise ValueError("El alumno no está matriculado en esta materia")
        if es_extra:
            from db.competencias_bach_ordinaria import (
                ensure_snapshot_ordinaria_grupo,
                mapa_snapshot_ordinaria,
            )

            ensure_snapshot_ordinaria_grupo(nombre)
            snap = mapa_snapshot_ordinaria(nombre)
            if materia_aprobada_ordinaria_alumno(meta, al_norm, snap):
                raise ValueError("Las notas aprobadas en ordinaria no se pueden editar")
            notas_acta_extra = mapa_notas_acta_valores(nombre, sesion="extraordinaria")
            notas_comp_extra = mapa_notas_comp_valores(nombre, sesion="extraordinaria")
            orig = _nota_acta_decimal(meta, al_norm, notas_acta_extra)
        else:
            orig = _nota_acta_decimal(meta, al_norm, notas_acta)
        original_str = (
            format_nota_acta_es(orig, cualitativa=cualitativa) if orig is not None else ""
        )
    else:
        from db.competencias_alumno_competencia import filas_competencia_por_alumno_grupo

        filas = filas_competencia_por_alumno_grupo(nombre, sesion=sesion).get(
            al_norm
        ) or []
        fila = next((f for f in filas if (f.get("abreviatura") or "").strip() == skey), None)
        original_str = (fila or {}).get("nota") or ""

    nueva_str = (
        format_nota_acta_es(nota_nueva, cualitativa=cualitativa)
        if nota_nueva is not None
        else ""
    )
    if nueva_str == original_str:
        guardar_override_sesion(
            grupo=nombre,
            sesion=sesion,
            alumno=al_canon,
            scope=scope_v,
            scope_key=skey,
            nota=None,
            updated_by=updated_by,
        )
        editada = False
        nota_resp = original_str
    else:
        if nota_nueva is None:
            raise ValueError(
                "La nota de ESO debe ser IN, SU, BI, NT o SB"
                if cualitativa
                else "La nota debe ser un entero entre 0 y 10"
            )
        guardar_override_sesion(
            grupo=nombre,
            sesion=sesion,
            alumno=al_canon,
            scope=scope_v,
            scope_key=skey,
            nota=nota_nueva,
            updated_by=updated_by,
        )
        editada = True
        nota_resp = nueva_str

    overrides = mapa_overrides_sesion(nombre, sesion=sesion).get(al_norm) or {}
    curso_grupo = get_group_curso(nombre)
    stage = stage_of(grupo=nombre, curso=curso_grupo)
    snapshot_guard: dict = {}
    es_extra_sesion = es_extra and stage == "bachillerato"
    if es_extra_sesion:
        from db.competencias_bach_ordinaria import (
            ensure_snapshot_ordinaria_grupo,
            mapa_snapshot_ordinaria,
        )

        ensure_snapshot_ordinaria_grupo(nombre)
        snapshot_guard = mapa_snapshot_ordinaria(nombre)
        if not notas_acta_extra:
            notas_acta_extra = mapa_notas_acta_valores(nombre, sesion="extraordinaria")
            notas_comp_extra = mapa_notas_comp_valores(nombre, sesion="extraordinaria")
    curso_num = (
        extract_course_num(grupo=nombre, curso=curso_grupo, stage=stage)
        if stage
        else None
    )
    notas_decision = _notas_decision_alumno(
        agrupadas=agrupadas,
        al_norm=al_norm,
        notas_acta=notas_acta,
        notas_comp=notas_comp,
        sesion=sesion,
        overrides=overrides,
        snapshot=snapshot_guard,
        es_extra_sesion=es_extra_sesion,
        notas_acta_extra=notas_acta_extra,
        notas_comp_extra=notas_comp_extra,
    )
    if stage == "bachillerato":
        decision, decision_ok = _decision_bach(curso_num, notas_decision, sesion=sesion)
    else:
        decision, decision_ok = None, None

    return {
        "nota": nota_resp,
        "editada": editada,
        "decision": decision,
        "decision_ok": decision_ok,
    }


def datos_sesion_evaluacion_grupo(
    grupo: str,
    *,
    sesion: str | None = None,
) -> dict[str, Any]:
    """Alumnos, materias con nota_acta y competencias clave."""
    from db.competencias_alumno_competencia import competencias_vacias
    from db.competencias_evaluacion import (
        ensure_notas_comp_grupo,
        mapa_notas_acta_valores,
        mapa_notas_comp_valores,
    )
    from db.competencias_fechas_sesion import format_fecha_sesion, get_fecha_sesion, clave_sesion_fecha
    from db.competencias_sesion_notas import mapa_overrides_sesion
    from db.enrolled_subjects import _latest_import_id

    nombre = (grupo or "").strip()
    competencias_vacias_ui = competencias_vacias()

    alumnos = _alumnos_sesion(nombre)
    ensure_enrolled_subjects_schema()
    ensure_subject_catalog_schema()
    import_id = _latest_import_id()
    filas = _filas_materias_grupo(nombre=nombre, import_id=import_id) if import_id else []
    agrupadas = _agrupar_materias_filas(filas) if filas else []
    # Rellena nota_comp solo la primera vez (si hay criterios y aún no hay medias).
    ensure_notas_comp_grupo(nombre)
    notas_acta = mapa_notas_acta_valores(nombre)
    notas_comp = mapa_notas_comp_valores(nombre)
    notas_acta_extra: dict = {}
    notas_comp_extra: dict = {}
    overrides_grupo = mapa_overrides_sesion(nombre, sesion=sesion)
    curso_grupo = get_group_curso(nombre)
    stage = stage_of(grupo=nombre, curso=curso_grupo)
    curso_num = (
        extract_course_num(grupo=nombre, curso=curso_grupo, stage=stage)
        if stage
        else None
    )

    if not alumnos:
        vistos: set[str] = set()
        extra: list[dict[str, str]] = []
        for m in agrupadas:
            for al in sorted(m.get("alumnos") or [], key=normalize_for_sort):
                if al in vistos:
                    continue
                vistos.add(al)
                extra.append({"alumno": al, "fecha_nacimiento": ""})
        alumnos = extra

    es_extra_sesion = (
        (sesion or "").strip().lower() == "extraordinaria"
        and stage == "bachillerato"
    )
    snapshot: dict[tuple[str, int, str], dict[str, Decimal | None]] = {}
    if es_extra_sesion:
        from db.competencias_bach_ordinaria import (
            ensure_snapshot_ordinaria_grupo,
            mapa_snapshot_ordinaria,
        )

        ensure_snapshot_ordinaria_grupo(nombre)
        snapshot = mapa_snapshot_ordinaria(nombre)
        notas_acta_extra = mapa_notas_acta_valores(nombre, sesion="extraordinaria")
        notas_comp_extra = mapa_notas_comp_valores(nombre, sesion="extraordinaria")
        cohort = _cohorte_extraordinaria_bach(agrupadas, snapshot)
        alumnos = [a for a in alumnos if _al(a["alumno"]) in cohort]

    fichas: list[dict[str, Any]] = []
    for al in alumnos:
        al_norm = _al(al["alumno"])
        al_overrides = overrides_grupo.get(al_norm) or {}
        curso: list[dict[str, Any]] = []
        pendientes: list[dict[str, Any]] = []
        actuales_keys: set[tuple[Any, Any]] = set()
        for m in agrupadas:
            if al_norm not in (m.get("alumnos") or set()):
                continue
            item = _item_materia_sesion(
                m,
                al_norm,
                notas_acta,
                notas_comp,
                sesion=sesion,
                overrides=al_overrides,
                snapshot=snapshot,
                es_extra_sesion=es_extra_sesion,
                notas_acta_extra=notas_acta_extra,
                notas_comp_extra=notas_comp_extra,
            )
            if item["es_pendiente"]:
                pendientes.append(
                    {
                        **item,
                        "_key": (m.get("materia_key"), m.get("curso_asignatura")),
                    }
                )
            else:
                actuales_keys.add((m.get("materia_key"), m.get("curso_asignatura")))
                curso.append(item)
        pendientes_visibles = [
            {k: v for k, v in p.items() if k != "_key"}
            for p in pendientes
            if p["_key"] not in actuales_keys
        ]
        notas_decision = [m["_nota"] for m in curso] + [
            p["_nota"] for p in pendientes if p["_key"] not in actuales_keys
        ]
        media_mats = _media_notas_2d(
            [m.get("_nota_comp") for m in curso]
            + [p.get("_nota_comp") for p in pendientes_visibles]
        )
        if stage == "bachillerato":
            decision, decision_ok = _decision_bach(
                curso_num, notas_decision, sesion=sesion
            )
        else:
            decision, decision_ok = None, None
        for m in curso:
            m.pop("_nota", None)
            m.pop("_nota_comp", None)
        for p in pendientes_visibles:
            p.pop("_nota", None)
            p.pop("_nota_comp", None)
        fichas.append(
            {
                "alumno": al["alumno"],
                "fecha_nacimiento": al["fecha_nacimiento"],
                "materias_curso": curso,
                "materias_pendientes": pendientes_visibles,
                "media_materias": media_mats,
                "decision": decision,
                "decision_ok": decision_ok,
                "_al_norm": al_norm,
            }
        )

    etapa_db = None
    if stage == "bachillerato":
        etapa_db = "bach"
    elif stage == "eso":
        etapa_db = "eso"

    descriptores_por_alumno: dict[str, list[dict[str, str]]] = {}
    competencias_por_alumno: dict[str, list[dict[str, str]]] = {}
    if etapa_db:
        from db.competencias_alumno_competencia import filas_competencia_por_alumno_grupo
        from db.competencias_alumno_descriptor import filas_descriptor_por_alumno_grupo
        from db.competencias_clave import list_descriptores_operativos

        descriptores_por_alumno = filas_descriptor_por_alumno_grupo(
            nombre,
            etapa=etapa_db,
            sesion=sesion,
        )
        competencias_por_alumno = filas_competencia_por_alumno_grupo(
            nombre, sesion=sesion
        )
        from db.competencias_calculo_config import (
            get_calculo_config,
            nivel_coef_desde_peso,
        )
        from db.competencias_recalc import pesos_materias_por_competencia_grupo

        nivel_coef = nivel_coef_desde_peso(get_calculo_config().get("peso_periodos"))
        pesos_grupo = pesos_materias_por_competencia_grupo(
            nombre,
            etapa=etapa_db,
            sesion=sesion,
            nivel=nivel_coef,
        )
        vacias = [
            {
                "descriptor": d,
                "nota_do_0": "",
                "nota_do_1": "",
                "nota_do_2": "",
            }
            for d in list_descriptores_operativos(etapa_db)
        ]
        vacias_cc = competencias_vacias_ui
        for ficha in fichas:
            al_norm = ficha.pop("_al_norm", _al(ficha["alumno"]))
            ficha["descriptores_notas"] = descriptores_por_alumno.get(al_norm) or vacias
            comps = competencias_por_alumno.get(al_norm) or vacias_cc
            ficha["competencias"] = _aplicar_overrides_competencias(
                comps, overrides_grupo.get(al_norm) or {}
            )
            ficha["media_competencias"] = _media_competencias_filas(
                ficha["competencias"]
            )
            ficha["pesos_por_competencia"] = pesos_grupo.get(al_norm) or {}
            ficha["nivel_coef_pesos"] = nivel_coef
    else:
        for ficha in fichas:
            ficha.pop("_al_norm", None)
            ficha["descriptores_notas"] = []
            ficha["competencias"] = competencias_vacias_ui
            ficha["media_competencias"] = ""
            ficha["pesos_por_competencia"] = {}
            ficha["nivel_coef_pesos"] = 0

    from db.competencias_clave import COMPETENCIAS_CLAVE_SEED

    return {
        "fecha_sesion": format_fecha_sesion(
            get_fecha_sesion(
                grupo=nombre,
                sesion=clave_sesion_fecha(grupo=nombre, stage=stage, sesion=sesion),
            )
        )
        or "—",
        "alumnos": fichas,
        "competencias": competencias_vacias_ui,
        "competencias_clave": [
            {"abreviatura": c["abreviatura"], "nombre": c["nombre"]}
            for c in COMPETENCIAS_CLAVE_SEED
        ],
    }


def cadena_calculo_alumno(
    grupo: str,
    alumno: str,
    *,
    sesion: str | None = None,
) -> dict[str, Any]:
    """Traza materias → aportaciones → suma_*/nota_do_* de un alumno."""
    from db.competencias_alumno_competencia import filas_competencia_por_alumno_grupo
    from db.competencias_alumno_descriptor import (
        ensure_competencias_alumno_descriptor_schema,
        format_nota_do_es,
        table_descriptor,
    )
    from db.competencias_calculo_config import (
        divisor_pendientes,
        get_calculo_config,
        nivel_coef_desde_peso,
    )
    from db.competencias_evaluacion import (
        acta_es_cualitativa,
        format_nota_acta_es,
        format_nota_materia_es,
        mapa_notas_acta_valores,
        mapa_notas_comp_valores,
    )
    from db.competencias_recalc import (
        _agregar_descriptores,
        _aportaciones,
        _load_matriculas_por_grupo,
        _load_notas_index,
        _load_pesos_index,
        _sesion_es_extraordinaria,
        _snapshot_ordinaria_grupo,
    )

    nombre = (grupo or "").strip()
    buscado = _al(alumno)
    if not nombre or not buscado:
        raise ValueError("Grupo o alumno no indicado")

    mats = _load_matriculas_por_grupo(nombre)
    data = mats.get(nombre)
    if not data:
        for gname, payload in mats.items():
            if gname.casefold() == nombre.casefold():
                data = payload
                nombre = gname
                break
    if not data:
        raise ValueError("Grupo sin matrículas")

    al_norm = None
    al_canon = None
    for k, v in data["alumnos"].items():
        if buscado == k or buscado in k or buscado in _al(v):
            al_norm = k
            al_canon = v
            break
    if not al_norm:
        raise ValueError(f"Alumno no encontrado en {nombre}")

    ms = data["materias"].get(al_norm) or []
    notas = _load_notas_index(grupo=nombre, sesion=sesion)
    acta = mapa_notas_acta_valores(nombre, sesion=sesion)
    ncomp = mapa_notas_comp_valores(nombre, sesion=sesion)
    pesos = _load_pesos_index()
    cfg = get_calculo_config()
    nivel = nivel_coef_desde_peso(cfg.get("peso_periodos"))
    div = divisor_pendientes(cfg.get("tratamiento_pendientes"))
    es_extra = _sesion_es_extraordinaria(sesion)
    snap = _snapshot_ordinaria_grupo(nombre, data["etapa"]) if es_extra else {}
    tbl_do = table_descriptor(sesion)

    materias_out: list[dict[str, Any]] = []
    for etapa_m, curso_m, key_m, es_pend in ms:
        ncrit = 0
        for key in notas:
            if (
                key[1] == al_norm
                and key[2] == etapa_m
                and key[3] == curso_m
                and key[4] == key_m
            ):
                ncrit += 1
        av = None
        cv = None
        for gk, mp in acta.items():
            if gk[0] == etapa_m and gk[1] == curso_m and gk[2] == key_m and al_norm in mp:
                av = mp[al_norm]
                break
        for gk, mp in ncomp.items():
            if gk[0] == etapa_m and gk[1] == curso_m and gk[2] == key_m and al_norm in mp:
                cv = mp[al_norm]
                break
        n_pesos = sum(len(pares) for pares in (pesos.get((etapa_m, curso_m, key_m)) or {}).values())
        # Criterios con nota vs criterios en pesos (para detectar desajuste de claves).
        crits_nota: list[str] = []
        for key in notas:
            if (
                key[1] == al_norm
                and key[2] == etapa_m
                and key[3] == curso_m
                and key[4] == key_m
            ):
                crits_nota.append(key[5])
        crits_peso: set[str] = set()
        for pares in (pesos.get((etapa_m, curso_m, key_m)) or {}).values():
            for crit, *_rest in pares:
                crits_peso.add(crit)
        # Búsqueda ampliada: mismas notas del alumno para keys parecidas (diagnóstico).
        otras_keys: dict[str, int] = {}
        for key in notas:
            if key[1] != al_norm:
                continue
            if "lengua" in key[4].casefold() or "lengua" in key_m.casefold():
                otras_keys[f"{key[2]}|{key[3]}|{key[4]}"] = otras_keys.get(
                    f"{key[2]}|{key[3]}|{key[4]}", 0
                ) + 1
        overlap = sorted(set(crits_nota) & crits_peso)
        solo_nota = sorted(set(crits_nota) - crits_peso)
        solo_peso = sorted(crits_peso - set(crits_nota))
        materias_out.append(
            {
                "etapa": etapa_m,
                "curso": curso_m,
                "materia_key": key_m,
                "pendiente": es_pend,
                "n_criterios_con_nota": ncrit,
                "n_pares_peso": n_pesos,
                "nota_acta": format_nota_acta_es(
                    av, cualitativa=acta_es_cualitativa(etapa_m)
                )
                if av is not None
                else "",
                "nota_comp": format_nota_materia_es(cv) if cv is not None else "",
                "criterios_nota": sorted(crits_nota),
                "criterios_en_ambos": overlap[:40],
                "criterios_solo_en_notas": solo_nota[:40],
                "criterios_solo_en_pesos": solo_peso[:40],
                "otras_claves_lengua_en_notas": otras_keys,
            }
        )

    aport = _aportaciones(
        grupo=nombre,
        etapa=data["etapa"],
        alumnos={al_norm: al_canon},
        materias={al_norm: ms},
        pesos=pesos,
        notas=notas,
        divisor_pend=div,
        snapshot_ordinaria=snap,
    )
    aport_out = [
        {
            "materia_key": row[4],
            "curso": row[3],
            "descriptor": row[5],
            "suma_nota_0": str(row[6]),
            "suma_coef_0": str(row[7]),
            "suma_nota_1": str(row[8]),
            "suma_coef_1": str(row[9]),
            "suma_nota_2": str(row[10]),
            "suma_coef_2": str(row[11]),
            "do0": format_nota_do_es(
                None if Decimal(str(row[7] or 0)) == 0 else row[6] / row[7]
            ),
            "do1": format_nota_do_es(
                None if Decimal(str(row[9] or 0)) == 0 else row[8] / row[9]
            ),
            "do2": format_nota_do_es(
                None if Decimal(str(row[11] or 0)) == 0 else row[10] / row[11]
            ),
        }
        for row in aport
    ]

    dos_live = _agregar_descriptores(
        nombre, data["etapa"], {al_norm: al_canon}, aport
    )
    do_live_out = [
        {
            "descriptor": row[3],
            "suma_nota_0": str(row[4]),
            "suma_coef_0": str(row[5]),
            "nota_do_0": format_nota_do_es(row[6]),
            "suma_nota_1": str(row[7]),
            "suma_coef_1": str(row[8]),
            "nota_do_1": format_nota_do_es(row[9]),
            "suma_nota_2": str(row[10]),
            "suma_coef_2": str(row[11]),
            "nota_do_2": format_nota_do_es(row[12]),
        }
        for row in dos_live
    ]

    ensure_competencias_alumno_descriptor_schema()
    do_db_out: list[dict[str, str]] = []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT descriptor,
                       suma_nota_0, suma_coef_0, nota_do_0,
                       suma_nota_1, suma_coef_1, nota_do_1,
                       suma_nota_2, suma_coef_2, nota_do_2
                FROM {tbl_do}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                  AND LOWER(TRIM(alumno)) = LOWER(TRIM(%s))
                ORDER BY descriptor
                """,
                (nombre, al_canon),
            )
            for r in cur.fetchall():
                def _s(v):
                    return "" if v is None else str(v)

                def _ndo(v):
                    return format_nota_do_es(
                        None if v is None else Decimal(str(v))
                    )

                do_db_out.append(
                    {
                        "descriptor": str(r["descriptor"] or ""),
                        "suma_nota_0": _s(r.get("suma_nota_0")),
                        "suma_coef_0": _s(r.get("suma_coef_0")),
                        "nota_do_0": _ndo(r.get("nota_do_0")),
                        "suma_nota_1": _s(r.get("suma_nota_1")),
                        "suma_coef_1": _s(r.get("suma_coef_1")),
                        "nota_do_1": _ndo(r.get("nota_do_1")),
                        "suma_nota_2": _s(r.get("suma_nota_2")),
                        "suma_coef_2": _s(r.get("suma_coef_2")),
                        "nota_do_2": _ndo(r.get("nota_do_2")),
                    }
                )

    comps = filas_competencia_por_alumno_grupo(nombre, sesion=sesion).get(al_norm) or []

    return {
        "grupo": nombre,
        "alumno": al_canon,
        "etapa": data["etapa"],
        "sesion": "extraordinaria" if es_extra else "ordinaria",
        "config": cfg,
        "nivel_coef_activo": nivel,
        "materias": materias_out,
        "aportaciones": aport_out,
        "descriptores_recalc": do_live_out,
        "descriptores_bd": do_db_out,
        "competencias": [
            {
                "abreviatura": c.get("abreviatura"),
                "nota": c.get("nota"),
                "nota_2d": c.get("nota_2d"),
                "nota_cc_0": c.get("nota_cc_0"),
                "nota_cc_1": c.get("nota_cc_1"),
                "nota_cc_2": c.get("nota_cc_2"),
            }
            for c in comps
        ],
    }
