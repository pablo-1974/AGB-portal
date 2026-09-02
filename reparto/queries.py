"""Consultas de apoyo para el listado de departamentos en Reparto."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from db.connection import get_db
from db.departamentos import list_departamentos
from reparto.cache import (
    catalog_depto_map,
    bloques_fingerprint,
    get_cached_bloques,
    get_cached_snapshot,
    get_cached_viabilidad_bordes,
    invalidate_departamento_runtime_cache,
    set_cached_snapshot,
    set_cached_viabilidad_bordes,
    viabilidad_fingerprint,
)
from db.reparto_loader import load_control_horas_por_depto, load_departamento_snapshot, RepartoDepartamentoSnapshot
from db.reparto_miembros import HORAS_JORNADA_COMPLETA
from db.reparto_repartir_config import (
    MODOS_ELECCION,
    puede_elegir,
    sync_turno,
)
from reparto.viabilidad import (
    evaluar_bordes_reparto_turno,
    evaluar_eleccion_carga,
    evaluar_eleccion_otro,
    grupos_restantes_por_carga,
    grupos_restantes_por_otros,
    preparar_viabilidad_reparto,
    usuarios_con_tutoria,
)
from utils.text import normalize_for_sort


def list_profesores_departamento(*, nombre: str, abreviatura: str) -> list[dict]:
    """Profesorado activo cuyo campo departamento coincide con nombre o abreviatura."""
    nombre_n = (nombre or "").strip()
    abr_n = (abreviatura or "").strip()
    if not nombre_n and not abr_n:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, role, alias, departamento
                FROM users
                WHERE active = 1
                  AND COALESCE(status, 'activo') = 'activo'
                  AND LOWER(TRIM(COALESCE(role, ''))) <> 'invitado'
                  AND (
                    LOWER(BTRIM(COALESCE(departamento, ''))) = LOWER(BTRIM(%s))
                    OR LOWER(BTRIM(COALESCE(departamento, ''))) = LOWER(BTRIM(%s))
                  )
                """,
                (nombre_n, abr_n),
            )
            rows = [dict(r) for r in cur.fetchall()]
    rows.sort(
        key=lambda r: normalize_for_sort(
            str(r.get("alias") or r.get("name") or "")
        )
    )
    return rows


def miembros_tabla_departamento(*, nombre: str, abreviatura: str) -> list[dict]:
    """Filas de la tabla Miembros: alias, horas, jornada completa, no tutor."""
    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    return _miembros_desde_profesores(snap.profesores, snap.miembros_config)


def _dec(value) -> Decimal:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return Decimal(0)
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal(0)


def _fmt_dec(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f").rstrip("0").rstrip(".")


def control_filas() -> list[dict]:
    """Cuadre por departamento: horas de miembros vs resto (nominales + carga + otros)."""
    totales = load_control_horas_por_depto()
    filas = []
    for d in list_departamentos():
        abr = str(d.get("abreviatura") or "").strip()
        nom = str(d.get("departamento") or "").strip()
        t = totales.get(abr.lower()) or {}
        h_miembros = t.get("h_miembros") or Decimal(0)
        h_nominales = t.get("h_nominales") or Decimal(0)
        h_carga = t.get("h_carga") or Decimal(0)
        h_otros = t.get("h_otros") or Decimal(0)
        h_resto = h_nominales + h_carga + h_otros
        cuadran = h_miembros == h_resto and h_miembros != 0
        filas.append(
            {
                "departamento": nom,
                "abreviatura": abr,
                "horas_miembros": _fmt_dec(h_miembros),
                "horas_resto": _fmt_dec(h_resto),
                "ok": cuadran,
            }
        )
    return filas


CURSO_BLOCK_ORDER: list[tuple[str, int, str]] = [
    ("eso", 1, "1º ESO"),
    ("eso", 2, "2º ESO"),
    ("eso", 3, "3º ESO"),
    ("eso", 4, "4º ESO"),
    ("bach", 1, "1º Bach"),
    ("bach", 2, "2º Bach"),
    ("fpb", 1, "FPB 1"),
    ("fpb", 2, "FPB 2"),
    ("fpb", 3, "FPB 3"),
    ("fpb", 4, "FPB 4"),
]

BLOCK_THEMES = {
    "nominal": {"title": "#7dd3fc", "th": "#e0f2fe", "cell": "#f0f9ff", "label": "#0c4a6e"},
    "curso": [
        {"title": "#6ee7b7", "th": "#d1fae5", "cell": "#ecfdf5", "label": "#065f46"},
        {"title": "#34d399", "th": "#a7f3d0", "cell": "#d1fae5", "label": "#047857"},
        {"title": "#2dd4bf", "th": "#99f6e4", "cell": "#ccfbf1", "label": "#0f766e"},
        {"title": "#4ade80", "th": "#bbf7d0", "cell": "#dcfce7", "label": "#166534"},
    ],
    "externo": {"title": "#fbbf24", "th": "#fef3c7", "cell": "#fffbeb", "label": "#92400e"},
    "otros": {"title": "#c4b5fd", "th": "#ede9fe", "cell": "#f5f3ff", "label": "#5b21b6"},
}


def _miembros_desde_profesores(
    profesores: list[dict],
    saved: dict[int, dict],
) -> list[dict]:
    out: list[dict] = []
    for p in profesores:
        uid = int(p["id"])
        cfg = saved.get(uid) or {}
        if cfg.get("excluido"):
            continue
        jornada = cfg.get("jornada_completa", True)
        horas = HORAS_JORNADA_COMPLETA if jornada else int(cfg.get("horas") or HORAS_JORNADA_COMPLETA)
        alias = (str(p.get("alias") or "").strip() or str(p.get("name") or "").strip())
        out.append(
            {
                "user_id": uid,
                "alias": alias,
                "horas": horas,
                "jornada_completa": jornada,
                "no_tutor": bool(cfg.get("no_tutor", False)),
                "tipo": cfg.get("tipo") or "",
                "orden": cfg.get("orden"),
            }
        )
    n = len(out)
    used: set[int] = set()
    for m in out:
        o = m.get("orden")
        if isinstance(o, int) and 1 <= o <= n and o not in used:
            used.add(o)
        else:
            m["orden"] = None
    nxt = 1
    for m in out:
        if m.get("orden"):
            continue
        while nxt in used:
            nxt += 1
        m["orden"] = nxt
        used.add(nxt)
    out.sort(key=lambda m: (int(m["orden"]), normalize_for_sort(str(m.get("alias") or ""))))
    return out


def _catalog_depto_map() -> dict[str, str]:
    return catalog_depto_map()


def _materia_es_depto(
    item: dict,
    *,
    depto_nombre: str,
    depto_abrev: str,
    catalog_map: dict[str, str],
) -> bool:
    ck = str(item.get("curso_key") or "")
    parts = ck.split("|", 1)
    etapa = parts[0] if parts else ""
    curso = parts[1] if len(parts) > 1 else ""
    mab = str(item.get("materia_abrev") or "").strip().lower()
    key = f"{etapa}|{curso}|{mab}"
    dep = (catalog_map.get(key) or "").strip()
    if not dep:
        return False
    dep_l = dep.lower()
    nom_l = (depto_nombre or "").strip().lower()
    abr_l = (depto_abrev or "").strip().lower()
    return dep_l == nom_l or dep_l == abr_l


def _grupos_int(grupos: str) -> int:
    raw = str(grupos or "").strip().replace(",", ".")
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        d = _dec(raw)
        if d == d.to_integral_value():
            return max(0, int(d))
        return 0


def _nominal_slots(grupos: str) -> int:
    g = _grupos_int(str(grupos or ""))
    return max(1, g) if g > 0 else 1


def _nominales_completas(
    nominales: list[dict],
    nominal_asignados_col: dict[int, int],
) -> bool:
    if not nominales:
        return True
    for n in nominales:
        hn_id = int(n["id"])
        slots = _nominal_slots(str(n.get("grupos") or ""))
        if nominal_asignados_col.get(hn_id, 0) < slots:
            return False
    return True


def _nominal_grupos_elegidos(col: dict) -> str:
    g = _grupos_int(str(col.get("grupos") or ""))
    return str(g) if g > 0 else "1"


def _grupos_restantes_col(
    col: dict,
    nominal_asignados_col: dict[int, int],
    carga_asignados_col: dict[int, int],
    otro_asignados_col: dict[int, int],
) -> str:
    total = _grupos_int(str(col.get("grupos") or ""))
    col_tipo = str(col.get("col_tipo") or "")
    if col_tipo == "nominal":
        slots = _nominal_slots(str(col.get("grupos") or ""))
        used = nominal_asignados_col.get(int(col["id"]), 0)
        return str(max(0, slots - used))
    elif col_tipo == "otro":
        slots = _nominal_slots(str(col.get("grupos") or ""))
        used = otro_asignados_col.get(int(col["id"]), 0)
        return str(max(0, slots - used))
    elif col_tipo == "carga":
        used = carga_asignados_col.get(int(col["id"]), 0)
        if total > 0:
            return str(max(0, total - used))
        return ""
    if total > 0:
        return str(total)
    return ""


def _title_row_height(bloques: list[dict]) -> str:
    max_len = 0
    for bloque in bloques:
        for col in bloque.get("columnas") or []:
            max_len = max(max_len, len(str(col.get("titulo") or "")))
    rem = max(4.5, min(11.0, 2.5 + max_len * 0.62))
    return f"{rem:.2f}rem"


def _abrev_display(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if "-" in s:
        tail = s.rsplit("-", 1)[-1].strip()
        if tail:
            return tail
    return s


def _carga_columna(it: dict) -> dict:
    abrev = _abrev_display(str(it.get("materia_abrev") or "").strip())
    if not abrev:
        abrev = _abrev_display(str(it.get("materia") or "").strip())
    if not abrev:
        abrev = str(it.get("materia") or "").strip()
    nombre = str(it.get("materia") or abrev).strip()
    titulo = abrev or nombre
    if it.get("tutoria"):
        titulo = f"{titulo} (T)"
    if it.get("dc"):
        titulo = f"{titulo} DC"
    return {
        "col_tipo": "carga",
        "id": int(it["id"]),
        "titulo": titulo,
        "nombre_completo": nombre,
        "horas": it.get("horas_por_grupo") or "",
        "grupos": it.get("grupos") or "",
        "tutoria": bool(it.get("tutoria")),
        "profesores_distintos": max(1, int(it.get("profesores_distintos") or 1)),
    }


def _otro_columna(o: dict) -> dict:
    return {
        "col_tipo": "otro",
        "id": int(o["id"]),
        "titulo": str(o.get("concepto") or "").strip() or "—",
        "horas": o.get("horas_por_grupo") or "",
        "grupos": o.get("grupos") or "",
    }


def _nominal_columna(n: dict) -> dict:
    titulo = str(n.get("concepto") or "").strip() or "—"
    return {
        "col_tipo": "nominal",
        "id": int(n["id"]),
        "titulo": titulo,
        "horas": n.get("horas_por_grupo") or "",
        "horas_totales": n.get("horas_totales") or "",
        "grupos": n.get("grupos") or "",
        "concepto": titulo,
    }


def _repartir_bloques(
    *,
    nombre: str,
    abreviatura: str,
    nominales: list[dict],
    carga_items: list[dict],
    otros_items: list[dict],
) -> list[dict]:
    bloques: list[dict] = []
    catalog_map = _catalog_depto_map()
    depto_items = [
        it for it in carga_items
        if _materia_es_depto(
            it,
            depto_nombre=nombre,
            depto_abrev=abreviatura,
            catalog_map=catalog_map,
        )
    ]
    externos = [
        it for it in carga_items
        if not _materia_es_depto(
            it,
            depto_nombre=nombre,
            depto_abrev=abreviatura,
            catalog_map=catalog_map,
        )
    ]
    curso_hue = 0

    if nominales:
        theme = BLOCK_THEMES["nominal"]
        bloques.append(
            {
                "tipo": "nominal",
                "titulo": "Horas nominales",
                "theme": theme,
                "columnas": [_nominal_columna(n) for n in nominales],
            }
        )

    by_curso_key: dict[str, list[dict]] = {}
    for it in depto_items:
        ck = str(it.get("curso_key") or "")
        by_curso_key.setdefault(ck, []).append(it)

    for etapa, curso, titulo in CURSO_BLOCK_ORDER:
        ck = f"{etapa}|{curso}"
        items = by_curso_key.get(ck) or []
        if not items:
            continue
        palette = BLOCK_THEMES["curso"]
        theme = palette[curso_hue % len(palette)]
        curso_hue += 1
        bloques.append(
            {
                "tipo": "curso",
                "titulo": titulo,
                "theme": theme,
                "columnas": [_carga_columna(it) for it in items],
            }
        )

    for ck, items in by_curso_key.items():
        if any(f"{et}|{c}" == ck for et, c, _ in CURSO_BLOCK_ORDER):
            continue
        if not items:
            continue
        label = str(items[0].get("curso_label") or ck).strip() or ck
        palette = BLOCK_THEMES["curso"]
        theme = palette[curso_hue % len(palette)]
        curso_hue += 1
        bloques.append(
            {
                "tipo": "curso",
                "titulo": label,
                "theme": theme,
                "columnas": [_carga_columna(it) for it in items],
            }
        )

    if externos:
        bloques.append(
            {
                "tipo": "externo",
                "titulo": "Externos",
                "theme": BLOCK_THEMES["externo"],
                "columnas": [_carga_columna(it) for it in externos],
            }
        )

    if otros_items:
        bloques.append(
            {
                "tipo": "otros",
                "titulo": "Otros",
                "theme": BLOCK_THEMES["otros"],
                "columnas": [_otro_columna(o) for o in otros_items],
            }
        )

    return bloques


def _grupos_restantes_por_columna(
    bloques: list[dict],
    nominal_asignados_col: dict[int, int],
    carga_asignados_col: dict[int, int],
    otro_asignados_col: dict[int, int],
) -> dict[tuple[str, int], str]:
    out: dict[tuple[str, int], str] = {}
    for bloque in bloques:
        for col in bloque.get("columnas") or []:
            col_tipo = str(col.get("col_tipo") or "")
            out[(col_tipo, int(col["id"]))] = _grupos_restantes_col(
                col,
                nominal_asignados_col,
                carga_asignados_col,
                otro_asignados_col,
            )
    return out


def _carga_cols_map(carga_items: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for it in carga_items:
        col = _carga_columna(it)
        out[int(col["id"])] = col
    return out


def _otros_cols_map(otros_items: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for o in otros_items:
        col = _otro_columna(o)
        out[int(col["id"])] = col
    return out


def _horas_nominales_por_user(
    nominales: list[dict],
    nominal_counts_user: dict[tuple[int, int], int],
) -> tuple[dict[int, Decimal], dict[int, int]]:
    horas: dict[int, Decimal] = {}
    elecciones: dict[int, int] = {}
    nominal_by_id = {int(n["id"]): n for n in nominales}
    for (hn_id, uid), count in nominal_counts_user.items():
        n = nominal_by_id.get(int(hn_id))
        if not n or int(count) <= 0:
            continue
        uid = int(uid)
        c = int(count)
        horas[uid] = horas.get(uid, Decimal(0)) + _dec(n.get("horas_por_grupo")) * c
        elecciones[uid] = elecciones.get(uid, 0) + c
    return horas, elecciones


def _horas_otros_por_user(
    otros_items: list[dict],
    otro_counts_user: dict[tuple[int, int], int],
) -> tuple[dict[int, Decimal], dict[int, int]]:
    horas: dict[int, Decimal] = {}
    elecciones: dict[int, int] = {}
    otro_by_id = {int(o["id"]): o for o in otros_items}
    for (o_id, uid), count in otro_counts_user.items():
        o = otro_by_id.get(int(o_id))
        if not o or int(count) <= 0:
            continue
        uid = int(uid)
        c = int(count)
        horas[uid] = horas.get(uid, Decimal(0)) + _dec(o.get("horas_por_grupo")) * c
        elecciones[uid] = elecciones.get(uid, 0) + c
    return horas, elecciones


def _horas_carga_y_elecciones(
    carga_counts_user: dict[tuple[int, int], int],
    carga_cols: dict[int, dict],
) -> tuple[dict[int, Decimal], dict[int, int]]:
    horas_carga_por_user: dict[int, Decimal] = {}
    elecciones_por_user: dict[int, int] = {}
    for (cid, uid_k), count in carga_counts_user.items():
        col_c = carga_cols.get(int(cid))
        if not col_c:
            continue
        uid_k = int(uid_k)
        n = int(count)
        horas_carga_por_user[uid_k] = horas_carga_por_user.get(uid_k, Decimal(0)) + (
            _dec(col_c.get("horas")) * n
        )
        elecciones_por_user[uid_k] = elecciones_por_user.get(uid_k, 0) + n
    return horas_carga_por_user, elecciones_por_user


def _filas_resumen_reparto(
    miembros: list[dict],
    horas_nominales_por_user: dict[int, Decimal],
    horas_carga_por_user: dict[int, Decimal],
    elecciones_por_user: dict[int, int],
    horas_otros_por_user: dict[int, Decimal] | None = None,
) -> list[dict]:
    filas: list[dict] = []
    horas_otros_map = horas_otros_por_user or {}
    for m in miembros:
        uid = int(m["user_id"])
        jornada = int(m.get("horas") or 0)
        horas_nominales = horas_nominales_por_user.get(uid, Decimal(0))
        horas_carga = horas_carga_por_user.get(uid, Decimal(0))
        horas_otros = horas_otros_map.get(uid, Decimal(0))
        horas_restantes = _dec(jornada) - horas_nominales - horas_carga - horas_otros
        filas.append(
            {
                "user_id": uid,
                "jornada": jornada,
                "elecciones": elecciones_por_user.get(uid, 0),
                "nombre": str(m.get("alias") or ""),
                "tipo": str(m.get("tipo") or ""),
                "orden": int(m.get("orden") or 0),
                "horas": _fmt_dec(horas_restantes),
                "horas_val": horas_restantes,
                "horas_ok": horas_restantes == 0,
                "no_tutor": bool(m.get("no_tutor")),
            }
        )
    return filas


def _semaforo_estado_turno(
    filas: list[dict],
    *,
    turno_user_id: int | None,
    nominales_completas: bool,
) -> str:
    """
    Estado del semáforo según bordes del profesor con turno en columnas no agotadas.
    verde | mixto | naranja
    """
    if not nominales_completas or turno_user_id is None:
        return "verde"
    fila = next(
        (f for f in filas if int(f["user_id"]) == int(turno_user_id)),
        None,
    )
    if not fila or not fila.get("puede_elegir"):
        return "verde"
    verdes = 0
    rojos = 0
    for cell in fila.get("eleccion_cells") or []:
        if not _celda_eleccion_viable(cell):
            continue
        borde = cell.get("borde_eleccion")
        if borde == "verde":
            verdes += 1
        elif borde == "rojo":
            rojos += 1
    total = verdes + rojos
    if total == 0:
        return "verde"
    if verdes == total:
        return "verde"
    if verdes == 1:
        return "naranja"
    if verdes > 1 and rojos > 0:
        return "mixto"
    return "naranja"


def _celda_carga_viable(cell: dict) -> bool:
    """Columna de carga con grupos restantes donde aún puede elegir."""
    if cell.get("col_tipo") != "carga" or cell.get("mostrar_x"):
        return False
    if cell.get("col_sin_grupos"):
        return False
    try:
        rest = int(cell.get("grupos_restantes_col") or 0)
    except (TypeError, ValueError):
        rest = 0
    return rest > 0


def _celda_otro_viable(cell: dict) -> bool:
    """Columna Otros con grupos restantes."""
    if cell.get("col_tipo") != "otro" or cell.get("mostrar_x"):
        return False
    if cell.get("col_sin_grupos"):
        return False
    try:
        rest = int(cell.get("grupos_restantes_col") or 0)
    except (TypeError, ValueError):
        rest = 0
    return rest > 0


def _celda_eleccion_viable(cell: dict) -> bool:
    """Carga u Otros con grupos restantes (elección de turno)."""
    if cell.get("col_tipo") == "carga":
        return _celda_carga_viable(cell)
    if cell.get("col_tipo") == "otro":
        return _celda_otro_viable(cell)
    return False


def _reparto_completado(
    filas: list[dict],
    grupos_cells: list[dict],
    nominales_completas: bool,
) -> bool:
    """Todos los grupos asignados y todas las horas de profesores en 0."""
    if not nominales_completas or not filas:
        return False
    if any(not f.get("horas_ok") for f in filas):
        return False
    return not any(g.get("pendiente") for g in grupos_cells)


def _carga_cols_desde_bloques(bloques: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for bloque in bloques:
        for col in bloque.get("columnas") or []:
            if str(col.get("col_tipo") or "") == "carga":
                out[int(col["id"])] = col
    return out


def reparto_informe_departamento(
    *,
    nombre: str,
    abreviatura: str,
    snapshot: RepartoDepartamentoSnapshot | None = None,
) -> dict:
    """Informe de elecciones por profesor cuando el reparto está completado."""
    snap = snapshot or load_departamento_snapshot(
        nombre=nombre, abreviatura=abreviatura
    )
    tabla = repartir_tabla_departamento(
        nombre=nombre,
        abreviatura=abreviatura,
        calcular_viabilidad=False,
        snapshot=snap,
    )
    completado = bool(tabla.get("reparto_completado"))
    nominal_by_id = {int(n["id"]): n for n in snap.nominales}
    otro_by_id = {int(o["id"]): o for o in snap.otros_items}
    carga_cols = _carga_cols_desde_bloques(tabla.get("bloques") or [])
    profesores: list[dict] = []

    for fila in tabla.get("filas") or []:
        uid = int(fila["user_id"])
        nominales_eleccion: list[dict] = []
        for (hn_id, u), count in snap.nominal_counts_user.items():
            if int(u) != uid or int(count) <= 0:
                continue
            n = nominal_by_id.get(int(hn_id))
            if not n:
                continue
            col_nom = _nominal_columna(n)
            hpg = _dec(n.get("horas_por_grupo"))
            c = int(count)
            nominales_eleccion.append(
                {
                    "concepto": col_nom["titulo"],
                    "horas": _fmt_dec(hpg * c),
                    "grupos": str(c),
                }
            )

        carga_eleccion: list[dict] = []
        for (cid, u), count in snap.carga_counts_user.items():
            if int(u) != uid or int(count) <= 0:
                continue
            col = carga_cols.get(int(cid))
            if not col:
                continue
            hpg = _dec(col.get("horas"))
            horas_tot = hpg * int(count)
            carga_eleccion.append(
                {
                    "titulo": str(col.get("titulo") or ""),
                    "nombre": str(col.get("nombre_completo") or col.get("titulo") or ""),
                    "grupos": int(count),
                    "horas_por_grupo": _fmt_dec(hpg),
                    "horas": _fmt_dec(horas_tot),
                    "tutoria": bool(col.get("tutoria")),
                }
            )
        carga_eleccion.sort(key=lambda x: normalize_for_sort(x["titulo"]))

        for (o_id, u), count in snap.otro_counts_user.items():
            if int(u) != uid or int(count) <= 0:
                continue
            o = otro_by_id.get(int(o_id))
            if not o:
                continue
            col_otro = _otro_columna(o)
            hpg = _dec(o.get("horas_por_grupo"))
            c = int(count)
            carga_eleccion.append(
                {
                    "titulo": str(col_otro["titulo"] or ""),
                    "nombre": str(col_otro["titulo"] or ""),
                    "grupos": c,
                    "horas_por_grupo": _fmt_dec(hpg),
                    "horas": _fmt_dec(hpg * c),
                    "tutoria": False,
                }
            )
        carga_eleccion.sort(key=lambda x: normalize_for_sort(x["titulo"]))

        profesores.append(
            {
                "user_id": uid,
                "nombre": str(fila.get("nombre") or ""),
                "tipo": str(fila.get("tipo") or ""),
                "orden": int(fila.get("orden") or 0),
                "jornada": int(fila.get("jornada") or 0),
                "nominales": nominales_eleccion,
                "carga": carga_eleccion,
            }
        )

    modos = {m[0]: m[1] for m in MODOS_ELECCION}
    modo_id = str(tabla.get("modo_eleccion") or "")
    return {
        "completado": completado,
        "departamento": nombre,
        "abreviatura": abreviatura,
        "modo_eleccion": modo_id,
        "modo_eleccion_label": modos.get(modo_id, modo_id),
        "profesores": profesores,
    }


def _invalidate_reparto_runtime_cache(abreviatura: str) -> None:
    invalidate_departamento_runtime_cache(abreviatura)


def _commit_snapshot(
    abreviatura: str,
    snap: RepartoDepartamentoSnapshot,
) -> tuple[bool, RepartoDepartamentoSnapshot]:
    _invalidate_reparto_runtime_cache(abreviatura)
    set_cached_snapshot(abreviatura, snap)
    return True, snap


def repartir_tabla_departamento(
    *,
    nombre: str,
    abreviatura: str,
    calcular_viabilidad: bool = True,
    snapshot: RepartoDepartamentoSnapshot | None = None,
) -> dict:
    """Tabla de reparto: bloque miembros + bloques de elección (nominales, cursos, otros)."""
    if snapshot is not None:
        snap = snapshot
        set_cached_snapshot(abreviatura, snap)
    else:
        snap = get_cached_snapshot(abreviatura)
        if snap is None:
            snap = load_departamento_snapshot(
                nombre=nombre, abreviatura=abreviatura
            )
            set_cached_snapshot(abreviatura, snap)
    nominales = snap.nominales
    carga_items = snap.carga_items
    otros_items = snap.otros_items
    bloques_fp = bloques_fingerprint(nominales, carga_items, otros_items)
    bloques = get_cached_bloques(
        abreviatura,
        bloques_fp,
        lambda: _repartir_bloques(
            nombre=nombre,
            abreviatura=abreviatura,
            nominales=nominales,
            carga_items=carga_items,
            otros_items=otros_items,
        ),
    )
    nominal_counts_user = snap.nominal_counts_user
    nominal_asignados_col = snap.nominal_asignados_col
    otro_counts_user = snap.otro_counts_user
    otro_asignados_col = snap.otro_asignados_col
    carga_counts_user = snap.carga_counts_user
    carga_asignados_col = snap.carga_asignados_col
    miembros = _miembros_desde_profesores(snap.profesores, snap.miembros_config)
    cfg = snap.repartir_cfg
    modo = cfg["modo_eleccion"]
    carga_cols: dict[int, dict] = {}
    for bloque in bloques:
        for col in bloque.get("columnas") or []:
            if str(col.get("col_tipo") or "") == "carga":
                carga_cols[int(col["id"])] = col
    no_tutor_map = {int(m["user_id"]): bool(m.get("no_tutor")) for m in miembros}
    tutoria_ya = usuarios_con_tutoria(carga_counts_user, carga_cols)
    otros_cols = _otros_cols_map(otros_items)
    grupos_rest_map = grupos_restantes_por_carga(carga_cols, carga_asignados_col)
    grupos_rest_otros_map = grupos_restantes_por_otros(otros_cols, otro_asignados_col)
    grupos_rest_by_col = _grupos_restantes_por_columna(
        bloques, nominal_asignados_col, carga_asignados_col, otro_asignados_col
    )
    horas_nom_por_user, elecciones_nom_por_user = _horas_nominales_por_user(
        nominales, nominal_counts_user
    )
    horas_otros_por_user, elecciones_otro_por_user = _horas_otros_por_user(
        otros_items, otro_counts_user
    )
    horas_carga_por_user, elecciones_por_user = _horas_carga_y_elecciones(
        carga_counts_user, carga_cols
    )
    nominales_completas = _nominales_completas(nominales, nominal_asignados_col)

    filas = []
    for m in miembros:
        uid = int(m["user_id"])
        jornada = int(m.get("horas") or 0)
        elecciones = elecciones_por_user.get(uid, 0) + elecciones_otro_por_user.get(uid, 0)
        horas_nominales = horas_nom_por_user.get(uid, Decimal(0))
        horas_carga = horas_carga_por_user.get(uid, Decimal(0))
        horas_otros = horas_otros_por_user.get(uid, Decimal(0))
        eleccion_cells: list[dict] = []
        for bloque in bloques:
            for ci, col in enumerate(bloque["columnas"]):
                theme = bloque.get("theme") or {}
                block_start = ci == 0
                col_tipo = str(col.get("col_tipo") or "")
                col_key = (col_tipo, int(col["id"]))
                rest_col_str = grupos_rest_by_col.get(col_key, "")
                col_sin_grupos = rest_col_str == "0"
                if col_tipo == "nominal":
                    n_id = int(col["id"])
                    count = nominal_counts_user.get((n_id, uid), 0)
                    slots = _nominal_slots(str(col.get("grupos") or ""))
                    used_col = nominal_asignados_col.get(n_id, 0)
                    col_agotada = used_col >= slots
                    eleccion_cells.append(
                        {
                            "col_tipo": "nominal",
                            "nominal_id": n_id,
                            "grupos_elegidos": str(count) if count > 0 else "",
                            "elected": count > 0,
                            "puede_pulsar": not col_agotada,
                            "block_start": block_start,
                            "theme": theme,
                            "bloque_tipo": bloque.get("tipo"),
                            "col_sin_grupos": col_sin_grupos,
                        }
                    )
                elif col_tipo == "carga":
                    cid = int(col["id"])
                    count = carga_counts_user.get((cid, uid), 0)
                    rest_col = grupos_rest_map.get(cid, 0)
                    eleccion_cells.append(
                        {
                            "col_tipo": "carga",
                            "carga_id": cid,
                            "grupos_elegidos": str(count) if count > 0 else "",
                            "elected": count > 0,
                            "puede_pulsar": False,
                            "grupos_restantes_col": rest_col,
                            "horas_por_grupo": _dec(col.get("horas")),
                            "borde_eleccion": None,
                            "block_start": block_start,
                            "theme": theme,
                            "bloque_tipo": bloque.get("tipo"),
                            "col_sin_grupos": col_sin_grupos,
                        }
                    )
                else:
                    o_id = int(col["id"])
                    count = otro_counts_user.get((o_id, uid), 0)
                    rest_col = grupos_rest_otros_map.get(o_id, 0)
                    eleccion_cells.append(
                        {
                            "col_tipo": "otro",
                            "otro_id": o_id,
                            "grupos_elegidos": str(count) if count > 0 else "",
                            "elected": count > 0,
                            "puede_pulsar": False,
                            "grupos_restantes_col": rest_col,
                            "horas_por_grupo": _dec(col.get("horas")),
                            "borde_eleccion": None,
                            "block_start": block_start,
                            "theme": theme,
                            "bloque_tipo": bloque.get("tipo"),
                            "col_sin_grupos": col_sin_grupos,
                        }
                    )
        horas_restantes = _dec(jornada) - horas_nominales - horas_carga - horas_otros
        filas.append(
            {
                "user_id": uid,
                "jornada": jornada,
                "elecciones": elecciones,
                "nombre": str(m.get("alias") or ""),
                "tipo": str(m.get("tipo") or ""),
                "orden": int(m.get("orden") or 0),
                "horas": _fmt_dec(horas_restantes),
                "horas_val": horas_restantes,
                "horas_ok": horas_restantes == 0,
                "no_tutor": bool(m.get("no_tutor")),
                "tiene_tutoria": uid in tutoria_ya,
                "eleccion_cells": eleccion_cells,
            }
        )
    turno_uid = sync_turno(
        departamento_abrev=abreviatura,
        modo_eleccion=modo,
        filas=filas,
        turno_guardado=cfg.get("turno_user_id"),
    )
    turno_nombre = ""
    for f in filas:
        f["puede_elegir"] = nominales_completas and puede_elegir(
            user_id=int(f["user_id"]),
            turno_user_id=turno_uid,
            filas=filas,
            modo_eleccion=modo,
        )
        if nominales_completas and turno_uid is not None and int(f["user_id"]) == int(turno_uid):
            turno_nombre = str(f.get("nombre") or "")

    if calcular_viabilidad and nominales_completas:
        pendiente_carga_otros = any(
            int(n) > 0 for n in grupos_rest_map.values()
        ) or any(int(n) > 0 for n in grupos_rest_otros_map.values())
        if not pendiente_carga_otros:
            calcular_viabilidad = False

    if calcular_viabilidad:
        horas_map = {
            int(f["user_id"]): (
                f.get("horas_val")
                if isinstance(f.get("horas_val"), Decimal)
                else _dec(f.get("horas_val"))
            )
            for f in filas
        }
        turn_fila = next((f for f in filas if f.get("puede_elegir")), None)
        if turn_fila is not None:
            uid = int(turn_fila["user_id"])
            viab_fp = viabilidad_fingerprint(
                turno_user_id=turno_uid,
                horas_map=horas_map,
                grupos_rest_carga=grupos_rest_map,
                grupos_rest_otros=grupos_rest_otros_map,
                carga_counts_user=carga_counts_user,
            )
            cached_viab = get_cached_viabilidad_bordes(abreviatura, viab_fp)
            if cached_viab is not None:
                global_viable, bordes_carga, bordes_otro = cached_viab
            else:
                dist_init, global_viable, memo_viabilidad = preparar_viabilidad_reparto(
                    horas_map=horas_map,
                    grupos_rest_carga=grupos_rest_map,
                    carga_cols=carga_cols,
                    otros_cols=otros_cols,
                    grupos_rest_otros=grupos_rest_otros_map,
                    no_tutor=no_tutor_map,
                    tutoria_ya=tutoria_ya,
                    carga_counts_user=carga_counts_user,
                )
                carga_ids = [
                    int(c["carga_id"])
                    for c in turn_fila.get("eleccion_cells") or []
                    if _celda_carga_viable(c)
                ]
                otro_ids = [
                    int(c["otro_id"])
                    for c in turn_fila.get("eleccion_cells") or []
                    if _celda_otro_viable(c)
                ]
                bordes_carga, bordes_otro = evaluar_bordes_reparto_turno(
                    user_id=uid,
                    horas_map=horas_map,
                    grupos_rest_carga=grupos_rest_map,
                    carga_cols=carga_cols,
                    grupos_rest_otros=grupos_rest_otros_map,
                    otros_cols=otros_cols,
                    no_tutor=no_tutor_map,
                    tutoria_ya=tutoria_ya,
                    carga_ids=carga_ids,
                    otro_ids=otro_ids,
                    carga_counts_user=carga_counts_user,
                    dist_init=dist_init,
                    global_viable=global_viable,
                    memo=memo_viabilidad,
                )
                set_cached_viabilidad_bordes(
                    abreviatura,
                    viab_fp,
                    global_viable,
                    bordes_carga,
                    bordes_otro,
                )
            for cell in turn_fila.get("eleccion_cells") or []:
                tiene_eleccion = bool(cell.get("grupos_elegidos")) or bool(cell.get("elected"))
                cell["mostrar_x"] = bool(cell.get("col_sin_grupos")) and not tiene_eleccion
                if cell.get("col_tipo") == "nominal":
                    cell["borde_eleccion"] = None
                    continue
                if cell.get("col_tipo") == "otro":
                    if not _celda_otro_viable(cell):
                        cell["borde_eleccion"] = None
                        cell["puede_pulsar"] = False
                        continue
                    borde = bordes_otro.get(int(cell["otro_id"]), "rojo")
                    cell["borde_eleccion"] = borde
                    cell["puede_pulsar"] = borde == "verde"
                    continue
                if cell.get("col_tipo") != "carga":
                    continue
                if cell.get("mostrar_x"):
                    cell["borde_eleccion"] = None
                    cell["puede_pulsar"] = False
                    continue
                if not _celda_carga_viable(cell):
                    cell["borde_eleccion"] = None
                    cell["puede_pulsar"] = False
                    continue
                borde = bordes_carga.get(int(cell["carga_id"]), "rojo")
                cell["borde_eleccion"] = borde
                cell["puede_pulsar"] = borde == "verde"

    for f in filas:
        if calcular_viabilidad and f.get("puede_elegir"):
            continue
        for cell in f.get("eleccion_cells") or []:
            tiene_eleccion = bool(cell.get("grupos_elegidos")) or bool(cell.get("elected"))
            cell["mostrar_x"] = bool(cell.get("col_sin_grupos")) and not tiene_eleccion
            if cell.get("col_tipo") == "nominal":
                cell["borde_eleccion"] = None
                continue
            if cell.get("col_tipo") in ("carga", "otro"):
                if not f.get("puede_elegir"):
                    cell["borde_eleccion"] = None
                    if not tiene_eleccion:
                        cell["puede_pulsar"] = False
                elif not calcular_viabilidad and not tiene_eleccion:
                    cell["borde_eleccion"] = None
                    cell["puede_pulsar"] = False
                continue
            if not calcular_viabilidad or not f.get("puede_elegir"):
                cell["borde_eleccion"] = None
                cell["puede_pulsar"] = False

    grupos_cells: list[dict] = []
    for bloque in bloques:
        for ci, col in enumerate(bloque["columnas"]):
            theme = bloque.get("theme") or {}
            col_tipo = str(col.get("col_tipo") or "")
            rest = grupos_rest_by_col.get((col_tipo, int(col["id"])), "")
            grupos_cells.append(
                {
                    "grupos_restantes": rest,
                    "pendiente": bool(rest and rest != "0"),
                    "block_start": ci == 0,
                    "theme": theme,
                }
            )
    reparto_completado = _reparto_completado(
        filas, grupos_cells, nominales_completas
    )
    semaforo_estado = _semaforo_estado_turno(
        filas,
        turno_user_id=turno_uid if nominales_completas else None,
        nominales_completas=nominales_completas,
    )
    from db.reparto_pasos import count_pasos

    pasos_pendientes = count_pasos(abreviatura)
    return {
        "nominales": nominales,
        "bloques": bloques,
        "grupos_cells": grupos_cells,
        "title_row_height": _title_row_height(bloques),
        "filas": filas,
        "nominal_asignados_col": nominal_asignados_col,
        "modo_eleccion": modo,
        "turno_user_id": turno_uid if nominales_completas else None,
        "turno_nombre": turno_nombre,
        "nominales_completas": nominales_completas,
        "reparto_completado": reparto_completado,
        "semaforo_estado": semaforo_estado,
        "pasos_pendientes": pasos_pendientes,
    }


def asignar_otro_si_valida(
    *,
    nombre: str,
    abreviatura: str,
    otro_id: int,
    user_id: int,
) -> tuple[bool, RepartoDepartamentoSnapshot | None]:
    """Valida turno y viabilidad, asigna un grupo Otros y avanza turno."""
    from db.reparto_otro_asignaciones import add_otro_asignacion_and_set_turno
    from db.reparto_repartir_config import siguiente_turno

    o_id = int(otro_id)
    uid = int(user_id)
    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    if not _nominales_completas(snap.nominales, snap.nominal_asignados_col):
        return False, None

    otros_cols = _otros_cols_map(snap.otros_items)
    if o_id not in otros_cols:
        return False, None

    miembros = _miembros_desde_profesores(snap.profesores, snap.miembros_config)
    cfg = snap.repartir_cfg
    modo = cfg["modo_eleccion"]
    carga_cols = _carga_cols_map(snap.carga_items)

    horas_nom_por_user, _ = _horas_nominales_por_user(
        snap.nominales, snap.nominal_counts_user
    )
    horas_carga_por_user, elecciones_carga = _horas_carga_y_elecciones(
        snap.carga_counts_user, carga_cols
    )
    horas_otros_por_user, elecciones_otro = _horas_otros_por_user(
        snap.otros_items, snap.otro_counts_user
    )
    elecciones = dict(elecciones_carga)
    for u, n in elecciones_otro.items():
        elecciones[u] = elecciones.get(u, 0) + n
    filas = _filas_resumen_reparto(
        miembros,
        horas_nom_por_user,
        horas_carga_por_user,
        elecciones,
        horas_otros_por_user,
    )
    turno_uid = sync_turno(
        departamento_abrev=abreviatura,
        modo_eleccion=modo,
        filas=filas,
        turno_guardado=cfg.get("turno_user_id"),
    )
    if not puede_elegir(
        user_id=uid,
        turno_user_id=turno_uid,
        filas=filas,
        modo_eleccion=modo,
    ):
        return False, None

    no_tutor_map = {int(m["user_id"]): bool(m.get("no_tutor")) for m in miembros}
    tutoria_ya = usuarios_con_tutoria(snap.carga_counts_user, carga_cols)
    grupos_rest_map = grupos_restantes_por_carga(
        carga_cols, snap.carga_asignados_col
    )
    grupos_rest_otros_map = grupos_restantes_por_otros(
        otros_cols, snap.otro_asignados_col
    )
    horas_map = {int(f["user_id"]): f["horas_val"] for f in filas}

    dist_init, global_viable, memo = preparar_viabilidad_reparto(
        horas_map=horas_map,
        grupos_rest_carga=grupos_rest_map,
        carga_cols=carga_cols,
        otros_cols=otros_cols,
        grupos_rest_otros=grupos_rest_otros_map,
        no_tutor=no_tutor_map,
        tutoria_ya=tutoria_ya,
        carga_counts_user=snap.carga_counts_user,
    )
    if not global_viable:
        return False, None

    if evaluar_eleccion_otro(
        user_id=uid,
        otro_id=o_id,
        horas_map=horas_map,
        grupos_rest_carga=grupos_rest_map,
        carga_cols=carga_cols,
        grupos_rest_otros=grupos_rest_otros_map,
        otros_cols=otros_cols,
        no_tutor=no_tutor_map,
        tutoria_ya=tutoria_ya,
        carga_counts_user=snap.carga_counts_user,
        dist_init=dist_init,
        memo=memo,
    ) != "verde":
        return False, None

    otro = otros_cols[o_id]
    hpg = _dec(otro.get("horas"))
    horas_otros_por_user[uid] = horas_otros_por_user.get(uid, Decimal(0)) + hpg
    elecciones[uid] = elecciones.get(uid, 0) + 1
    filas = _filas_resumen_reparto(
        miembros,
        horas_nom_por_user,
        horas_carga_por_user,
        elecciones,
        horas_otros_por_user,
    )
    nuevo_turno = siguiente_turno(modo, filas, uid)
    ok = add_otro_asignacion_and_set_turno(
        departamento_abrev=abreviatura,
        otro_id=o_id,
        user_id=uid,
        turno_user_id=nuevo_turno,
    )
    if ok is None:
        return False, None
    snap.otro_counts_user[(o_id, uid)] = snap.otro_counts_user.get((o_id, uid), 0) + 1
    snap.otro_asignados_col[o_id] = snap.otro_asignados_col.get(o_id, 0) + 1
    snap.repartir_cfg["turno_user_id"] = nuevo_turno
    return _commit_snapshot(abreviatura, snap)


def asignar_nominal_si_valida(
    *,
    nombre: str,
    abreviatura: str,
    hora_nominal_id: int,
    user_id: int,
) -> tuple[bool, RepartoDepartamentoSnapshot | None]:
    """Añade un grupo nominal al profesor; inicia turno si se completan todas."""
    from db.reparto_nominal_asignaciones import add_nominal_asignacion
    from db.reparto_repartir_config import iniciar_turno_reparto

    hn_id = int(hora_nominal_id)
    uid = int(user_id)
    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    estaba_completo = _nominales_completas(
        snap.nominales, snap.nominal_asignados_col
    )
    if estaba_completo:
        return False, None

    ok = add_nominal_asignacion(
        departamento_abrev=abreviatura,
        hora_nominal_id=hn_id,
        user_id=uid,
    )
    if ok is None:
        return False, None

    snap.nominal_counts_user[(hn_id, uid)] = (
        snap.nominal_counts_user.get((hn_id, uid), 0) + 1
    )
    snap.nominal_asignados_col[hn_id] = snap.nominal_asignados_col.get(hn_id, 0) + 1

    ahora_completo = _nominales_completas(
        snap.nominales, snap.nominal_asignados_col
    )
    if ahora_completo and not estaba_completo:
        carga_cols = _carga_cols_map(snap.carga_items)
        miembros = _miembros_desde_profesores(snap.profesores, snap.miembros_config)
        horas_nom, _ = _horas_nominales_por_user(
            snap.nominales, snap.nominal_counts_user
        )
        horas_carga, elec_carga = _horas_carga_y_elecciones(
            snap.carga_counts_user, carga_cols
        )
        horas_otros, elec_otro = _horas_otros_por_user(
            snap.otros_items, snap.otro_counts_user
        )
        elecciones = dict(elec_carga)
        for u, n in elec_otro.items():
            elecciones[u] = elecciones.get(u, 0) + n
        filas = _filas_resumen_reparto(
            miembros, horas_nom, horas_carga, elecciones, horas_otros
        )
        iniciar_turno_reparto(
            departamento_abrev=abreviatura,
            modo_eleccion=str(snap.repartir_cfg.get("modo_eleccion") or ""),
            filas=filas,
        )
        snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)

    return _commit_snapshot(abreviatura, snap)


def asignar_carga_si_valida(
    *,
    nombre: str,
    abreviatura: str,
    carga_id: int,
    user_id: int,
) -> tuple[bool, RepartoDepartamentoSnapshot | None]:
    """Valida turno y viabilidad (rápido), asigna un grupo y avanza turno."""
    from db.reparto_carga_asignaciones import add_carga_asignacion_and_set_turno
    from db.reparto_repartir_config import siguiente_turno

    uid = int(user_id)
    cid = int(carga_id)
    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    carga_cols = _carga_cols_map(snap.carga_items)
    if cid not in carga_cols:
        return False, None

    miembros = _miembros_desde_profesores(snap.profesores, snap.miembros_config)
    cfg = snap.repartir_cfg
    modo = cfg["modo_eleccion"]

    nominales_completas = _nominales_completas(
        snap.nominales, snap.nominal_asignados_col
    )
    if not nominales_completas:
        return False, None

    horas_nom_por_user, _ = _horas_nominales_por_user(
        snap.nominales, snap.nominal_counts_user
    )
    horas_carga_por_user, elecciones_por_user = _horas_carga_y_elecciones(
        snap.carga_counts_user, carga_cols
    )
    horas_otros_por_user, elec_otro = _horas_otros_por_user(
        snap.otros_items, snap.otro_counts_user
    )
    elecciones = dict(elecciones_por_user)
    for u, n in elec_otro.items():
        elecciones[u] = elecciones.get(u, 0) + n
    filas = _filas_resumen_reparto(
        miembros,
        horas_nom_por_user,
        horas_carga_por_user,
        elecciones,
        horas_otros_por_user,
    )
    turno_uid = sync_turno(
        departamento_abrev=abreviatura,
        modo_eleccion=modo,
        filas=filas,
        turno_guardado=cfg.get("turno_user_id"),
    )
    if not puede_elegir(
        user_id=uid,
        turno_user_id=turno_uid,
        filas=filas,
        modo_eleccion=modo,
    ):
        return False, None

    no_tutor_map = {int(m["user_id"]): bool(m.get("no_tutor")) for m in miembros}
    tutoria_ya = usuarios_con_tutoria(snap.carga_counts_user, carga_cols)
    otros_cols = _otros_cols_map(snap.otros_items)
    grupos_rest_map = grupos_restantes_por_carga(carga_cols, snap.carga_asignados_col)
    grupos_rest_otros_map = grupos_restantes_por_otros(
        otros_cols, snap.otro_asignados_col
    )
    horas_map = {int(f["user_id"]): f["horas_val"] for f in filas}

    dist_init, global_viable, memo = preparar_viabilidad_reparto(
        horas_map=horas_map,
        grupos_rest_carga=grupos_rest_map,
        carga_cols=carga_cols,
        otros_cols=otros_cols,
        grupos_rest_otros=grupos_rest_otros_map,
        no_tutor=no_tutor_map,
        tutoria_ya=tutoria_ya,
        carga_counts_user=snap.carga_counts_user,
    )
    if not global_viable:
        return False, None

    if evaluar_eleccion_carga(
        user_id=uid,
        carga_id=cid,
        horas_map=horas_map,
        grupos_rest=grupos_rest_map,
        carga_cols=carga_cols,
        no_tutor=no_tutor_map,
        tutoria_ya=tutoria_ya,
        carga_counts_user=snap.carga_counts_user,
        otros_cols=otros_cols,
        grupos_rest_otros=grupos_rest_otros_map,
        dist_init=dist_init,
        memo=memo,
    ) != "verde":
        return False, None

    col = carga_cols[cid]
    hpg = _dec(col.get("horas"))
    horas_carga_por_user[uid] = horas_carga_por_user.get(uid, Decimal(0)) + hpg
    elecciones[uid] = elecciones.get(uid, 0) + 1
    filas = _filas_resumen_reparto(
        miembros,
        horas_nom_por_user,
        horas_carga_por_user,
        elecciones,
        horas_otros_por_user,
    )
    nuevo_turno = siguiente_turno(modo, filas, uid)
    ok = add_carga_asignacion_and_set_turno(
        departamento_abrev=abreviatura,
        carga_id=cid,
        user_id=uid,
        turno_user_id=nuevo_turno,
    )
    if ok is None:
        return False, None
    snap.carga_counts_user[(cid, uid)] = snap.carga_counts_user.get((cid, uid), 0) + 1
    snap.carga_asignados_col[cid] = snap.carga_asignados_col.get(cid, 0) + 1
    snap.repartir_cfg["turno_user_id"] = nuevo_turno
    return _commit_snapshot(abreviatura, snap)


def saltar_turno_departamento(
    *,
    nombre: str,
    abreviatura: str,
) -> tuple[bool, RepartoDepartamentoSnapshot | None]:
    """Avanza el turno sin elección de carga."""
    from db.reparto_repartir_config import saltar_turno_reparto

    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    cfg = snap.repartir_cfg
    modo = cfg["modo_eleccion"]

    nominales_completas = _nominales_completas(
        snap.nominales, snap.nominal_asignados_col
    )
    if not nominales_completas or cfg.get("turno_user_id") is None:
        return False, None

    carga_cols = _carga_cols_map(snap.carga_items)
    miembros = _miembros_desde_profesores(snap.profesores, snap.miembros_config)
    horas_nom_por_user, _ = _horas_nominales_por_user(
        snap.nominales, snap.nominal_counts_user
    )
    horas_carga_por_user, elecciones_por_user = _horas_carga_y_elecciones(
        snap.carga_counts_user, carga_cols
    )
    horas_otros_por_user, elec_otro = _horas_otros_por_user(
        snap.otros_items, snap.otro_counts_user
    )
    elecciones = dict(elecciones_por_user)
    for u, n in elec_otro.items():
        elecciones[u] = elecciones.get(u, 0) + n
    filas = _filas_resumen_reparto(
        miembros,
        horas_nom_por_user,
        horas_carga_por_user,
        elecciones,
        horas_otros_por_user,
    )

    nuevo = saltar_turno_reparto(
        departamento_abrev=abreviatura,
        filas=filas,
        modo_eleccion=modo,
    )
    snap.repartir_cfg["turno_user_id"] = nuevo
    return _commit_snapshot(abreviatura, snap)


def deshacer_ultimo_paso_departamento(
    *,
    nombre: str,
    abreviatura: str,
) -> tuple[bool, RepartoDepartamentoSnapshot | None]:
    """Deshace el último paso (nominal, carga, otros o saltar turno)."""
    from db.reparto_carga_asignaciones import delete_carga_asignacion_by_id
    from db.reparto_nominal_asignaciones import delete_nominal_asignacion_by_id
    from db.reparto_otro_asignaciones import delete_otro_asignacion_by_id
    from db.reparto_pasos import (
        delete_paso,
        get_ultimo_paso,
        TIPO_CARGA,
        TIPO_NOMINAL,
        TIPO_OTRO,
    )
    from db.reparto_repartir_config import set_turno_user_id

    paso = get_ultimo_paso(abreviatura)
    if not paso:
        return False, None

    tipo = str(paso.get("tipo") or "")
    reg_id = paso.get("registro_id")
    turno_restore = paso.get("turno_user_id")
    ok_paso = True

    if tipo == TIPO_NOMINAL and reg_id is not None:
        ok_paso = delete_nominal_asignacion_by_id(int(reg_id))
    elif tipo == TIPO_CARGA and reg_id is not None:
        ok_paso = delete_carga_asignacion_by_id(int(reg_id))
    elif tipo == TIPO_OTRO and reg_id is not None:
        ok_paso = delete_otro_asignacion_by_id(int(reg_id))

    if not ok_paso and reg_id is not None:
        return False, None

    set_turno_user_id(abreviatura, turno_restore)
    delete_paso(int(paso["id"]))
    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    return _commit_snapshot(abreviatura, snap)


def borrar_nominales_departamento(
    *,
    nombre: str,
    abreviatura: str,
) -> tuple[bool, RepartoDepartamentoSnapshot | None]:
    """Quita todas las asignaciones de horas nominales."""
    from db.reparto_nominal_asignaciones import clear_nominal_asignaciones
    from db.reparto_repartir_config import set_turno_user_id

    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    if not snap.nominales:
        return False, None
    clear_nominal_asignaciones(abreviatura)
    set_turno_user_id(abreviatura, None)
    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    return _commit_snapshot(abreviatura, snap)


def borrar_docencia_departamento(
    *,
    nombre: str,
    abreviatura: str,
) -> tuple[bool, RepartoDepartamentoSnapshot | None]:
    """Quita todas las elecciones de carga docente y Otros; reinicia el turno."""
    from db.reparto_carga_asignaciones import clear_carga_asignaciones
    from db.reparto_otro_asignaciones import clear_otro_asignaciones
    from db.reparto_repartir_config import iniciar_turno_reparto

    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    nominales_completas = _nominales_completas(
        snap.nominales, snap.nominal_asignados_col
    )
    if not nominales_completas:
        return False, None

    clear_carga_asignaciones(abreviatura)
    clear_otro_asignaciones(abreviatura)
    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    carga_cols = _carga_cols_map(snap.carga_items)
    miembros = _miembros_desde_profesores(snap.profesores, snap.miembros_config)
    horas_nom_por_user, _ = _horas_nominales_por_user(
        snap.nominales, snap.nominal_counts_user
    )
    horas_carga_por_user, elecciones_por_user = _horas_carga_y_elecciones(
        snap.carga_counts_user, carga_cols
    )
    horas_otros_por_user, elec_otro = _horas_otros_por_user(
        snap.otros_items, snap.otro_counts_user
    )
    elecciones = dict(elecciones_por_user)
    for u, n in elec_otro.items():
        elecciones[u] = elecciones.get(u, 0) + n
    filas = _filas_resumen_reparto(
        miembros,
        horas_nom_por_user,
        horas_carga_por_user,
        elecciones,
        horas_otros_por_user,
    )
    iniciar_turno_reparto(
        departamento_abrev=abreviatura,
        modo_eleccion=str(snap.repartir_cfg.get("modo_eleccion") or ""),
        filas=filas,
    )
    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    return _commit_snapshot(abreviatura, snap)


def borrar_todo_reparto_departamento(
    *,
    nombre: str,
    abreviatura: str,
) -> tuple[bool, RepartoDepartamentoSnapshot | None]:
    """Quita nominales, carga y otros para empezar el reparto de cero."""
    from db.reparto_carga_asignaciones import clear_carga_asignaciones
    from db.reparto_nominal_asignaciones import clear_nominal_asignaciones
    from db.reparto_otro_asignaciones import clear_otro_asignaciones
    from db.reparto_repartir_config import set_turno_user_id

    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    if not snap.nominales:
        return False, None

    tabla = repartir_tabla_departamento(
        nombre=nombre,
        abreviatura=abreviatura,
        calcular_viabilidad=False,
        snapshot=snap,
    )
    if not tabla.get("reparto_completado"):
        return False, None

    clear_carga_asignaciones(abreviatura)
    clear_otro_asignaciones(abreviatura)
    clear_nominal_asignaciones(abreviatura)
    set_turno_user_id(abreviatura, None)
    snap = load_departamento_snapshot(nombre=nombre, abreviatura=abreviatura)
    return _commit_snapshot(abreviatura, snap)
