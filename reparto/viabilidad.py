"""Viabilidad del reparto: cuadre de horas y restricciones de tutoría."""

from __future__ import annotations

from decimal import Decimal

ColCarga = tuple[int, Decimal, bool, int, int]


def _dec(value) -> Decimal:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return Decimal(0)
    try:
        return Decimal(raw)
    except Exception:
        return Decimal(0)


def usuarios_con_tutoria(
    carga_counts_user: dict[tuple[int, int], int],
    carga_cols: dict[int, dict],
) -> set[int]:
    out: set[int] = set()
    for (cid, uid), count in carga_counts_user.items():
        if int(count) <= 0:
            continue
        col = carga_cols.get(int(cid))
        if col and bool(col.get("tutoria")):
            out.add(int(uid))
    return out


def distintos_por_carga(
    carga_counts_user: dict[tuple[int, int], int],
) -> dict[int, frozenset[int]]:
    """Profesores que ya tienen grupos asignados en cada columna de carga."""
    tmp: dict[int, set[int]] = {}
    for (cid, uid), count in carga_counts_user.items():
        if int(count) <= 0:
            continue
        tmp.setdefault(int(cid), set()).add(int(uid))
    return {cid: frozenset(users) for cid, users in tmp.items()}


def grupos_restantes_por_carga(
    carga_cols: dict[int, dict],
    carga_asignados_col: dict[int, int],
) -> dict[int, int]:
    out: dict[int, int] = {}
    for cid, col in carga_cols.items():
        total = _grupos_int(str(col.get("grupos") or ""))
        used = int(carga_asignados_col.get(int(cid), 0))
        out[int(cid)] = max(0, total - used) if total > 0 else 0
    return out


def grupos_restantes_por_otros(
    otros_cols: dict[int, dict],
    otro_asignados_col: dict[int, int],
) -> dict[int, int]:
    out: dict[int, int] = {}
    for oid, col in otros_cols.items():
        total = _grupos_int(str(col.get("grupos") or ""))
        if total <= 0:
            total = 1
        used = int(otro_asignados_col.get(int(oid), 0))
        out[int(oid)] = max(0, total - used)
    return out


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


def _min_distinct(col: dict) -> int:
    try:
        d = int(col.get("profesores_distintos") or 1)
    except (TypeError, ValueError):
        d = 1
    return max(1, d)


def _columnas_desde_grupos(
    carga_cols: dict[int, dict],
    grupos_rest: dict[int, int],
) -> list[ColCarga]:
    """Columnas con grupos restantes: (carga_id, horas, tutoria, count, min_distinct)."""
    cols: list[ColCarga] = []
    for cid in sorted(grupos_rest.keys()):
        n = int(grupos_rest.get(cid, 0))
        if n <= 0:
            continue
        col = carga_cols.get(int(cid)) or {}
        h = _dec(col.get("horas"))
        tut = bool(col.get("tutoria"))
        md = _min_distinct(col)
        cols.append((int(cid), h, tut, n, md))
    cols.sort(key=lambda c: (c[2], c[1]), reverse=True)
    return cols


def _columnas_desde_otros(
    otros_cols: dict[int, dict],
    grupos_rest: dict[int, int],
) -> list[ColCarga]:
    """Slots Otros restantes agrupados por horas (menos ramas en búsqueda)."""
    buckets: dict[Decimal, int] = {}
    for oid in sorted(grupos_rest.keys()):
        n = int(grupos_rest.get(oid, 0))
        if n <= 0:
            continue
        col = otros_cols.get(int(oid)) or {}
        h = _dec(col.get("horas"))
        if h <= 0:
            continue
        buckets[h] = buckets.get(h, 0) + n
    cols: list[ColCarga] = []
    idx = 0
    for h in sorted(buckets.keys(), reverse=True):
        n = int(buckets[h])
        if n <= 0:
            continue
        idx += 1
        cols.append((-idx, h, False, n, 1))
    return cols


def _columnas_reparto(
    carga_cols: dict[int, dict],
    grupos_rest_carga: dict[int, int],
    otros_cols: dict[int, dict] | None,
    grupos_rest_otros: dict[int, int] | None,
) -> list[ColCarga]:
    cols = _columnas_desde_grupos(carga_cols, grupos_rest_carga)
    if otros_cols and grupos_rest_otros:
        cols.extend(_columnas_desde_otros(otros_cols, grupos_rest_otros))
    cols.sort(key=lambda c: (c[2], c[1]), reverse=True)
    return cols


def preparar_viabilidad_reparto(
    *,
    horas_map: dict[int, Decimal],
    grupos_rest_carga: dict[int, int],
    carga_cols: dict[int, dict],
    otros_cols: dict[int, dict] | None,
    grupos_rest_otros: dict[int, int] | None,
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    carga_counts_user: dict[tuple[int, int], int] | None = None,
) -> tuple[dict[int, frozenset[int]], bool, dict]:
    """Precalcula distintos, viabilidad global y memo compartido para el departamento."""
    dist_init = distintos_por_carga(carga_counts_user or {})
    cols_global = _columnas_reparto(
        carga_cols,
        grupos_rest_carga,
        otros_cols,
        grupos_rest_otros,
    )
    memo: dict = {}
    global_viable = _puede_completar_columnas(
        dict(horas_map),
        cols_global,
        no_tutor=no_tutor,
        tutoria_ya=tutoria_ya,
        distintos_inicial=dist_init,
        memo=memo,
    )
    return dist_init, global_viable, memo


def _pack_state(
    horas_mut: dict[int, Decimal],
    cols: list[ColCarga],
    col_idx: int,
    count_left: int,
    tut_mut: set[int],
    users_in_col: frozenset[int],
) -> tuple:
    hi = tuple(sorted((u, h) for u, h in horas_mut.items() if h > 0))
    ci = tuple((c[0], c[3], c[4]) for c in cols[col_idx:])
    if count_left > 0 and col_idx < len(cols):
        head = cols[col_idx]
        ci = ((head[0], count_left, head[4]),) + ci
    return (hi, ci, frozenset(tut_mut), users_in_col)


def puede_completar_reparto(
    horas: dict[int, Decimal],
    slots: list[tuple[Decimal, bool]],
    *,
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    memo: dict | None = None,
) -> bool:
    """¿Existe asignación de todos los slots que deja a cada profesor en 0 h?"""
    cols: list[ColCarga] = []
    slot_groups: dict[tuple[Decimal, bool], int] = {}
    for hpg, is_tut in slots:
        key = (hpg, is_tut)
        slot_groups[key] = slot_groups.get(key, 0) + 1
    idx = 0
    for (hpg, is_tut), count in sorted(slot_groups.items(), key=lambda x: (x[0][1], x[0][0]), reverse=True):
        cols.append((idx, hpg, is_tut, count, 1))
        idx += 1
    return _puede_completar_columnas(
        horas,
        cols,
        no_tutor=no_tutor,
        tutoria_ya=tutoria_ya,
        memo=memo,
    )


def _puede_completar_columnas(
    horas: dict[int, Decimal],
    cols: list[ColCarga],
    *,
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    distintos_inicial: dict[int, frozenset[int]] | None = None,
    memo: dict | None = None,
) -> bool:
    if not cols:
        return all(h <= 0 for h in horas.values())

    total_horas = sum(h for h in horas.values() if h > 0)
    total_slots = sum(c[1] * c[3] for c in cols)
    if total_horas != total_slots:
        return False

    tutoria_slots = sum(c[3] for c in cols if c[2])
    tutoria_capacidad = sum(
        1
        for uid, h in horas.items()
        if h > 0 and not no_tutor.get(uid, False) and uid not in tutoria_ya
    )
    if tutoria_slots > tutoria_capacidad:
        return False

    horas_mut = {uid: h for uid, h in horas.items() if h > 0}
    tut_mut: set[int] = set(tutoria_ya)
    cols_mut = list(cols)
    cache = memo if memo is not None else {}
    dist_init = distintos_inicial or {}

    def rec(
        col_idx: int,
        count_left: int | None = None,
        users_in_col: set[int] | None = None,
    ) -> bool:
        if count_left is None:
            if col_idx >= len(cols_mut):
                return all(h <= 0 for h in horas_mut.values())
            cid = cols_mut[col_idx][0]
            users_in_col = set(dist_init.get(cid, frozenset()))
            count_left = cols_mut[col_idx][3]

        while col_idx < len(cols_mut) and cols_mut[col_idx][3] <= 0:
            col_idx += 1
            count_left = None
            if col_idx >= len(cols_mut):
                return all(h <= 0 for h in horas_mut.values())

        if count_left is None:
            return rec(col_idx)

        if count_left <= 0:
            min_d = cols_mut[col_idx][4]
            if len(users_in_col or set()) < min_d:
                return False
            return rec(col_idx + 1)

        rest_horas = sum(horas_mut.values())
        rest_slots = Decimal(0)
        for ci in range(col_idx, len(cols_mut)):
            c = cols_mut[ci]
            n_slots = c[3] if ci != col_idx else count_left
            rest_slots += c[1] * Decimal(int(n_slots))
        if rest_horas != rest_slots:
            key = _pack_state(
                horas_mut, cols_mut, col_idx, count_left, tut_mut,
                frozenset(users_in_col or set()),
            )
            cache[key] = False
            return False

        users_set = users_in_col or set()
        key = _pack_state(horas_mut, cols_mut, col_idx, count_left, tut_mut, frozenset(users_set))
        cached = cache.get(key)
        if cached is not None:
            return cached

        _, hpg, is_tut, _, _ = cols_mut[col_idx]
        candidatos = sorted(
            horas_mut.keys(),
            key=lambda u: (
                0 if horas_mut[u] == hpg else 1,
                -int(horas_mut[u]),
            ),
        )
        result = False
        for uid in candidatos:
            if horas_mut[uid] < hpg:
                continue
            if is_tut and (no_tutor.get(uid, False) or uid in tut_mut):
                continue
            horas_mut[uid] -= hpg
            if is_tut:
                tut_mut.add(uid)
            next_users = users_set
            if uid not in users_set:
                next_users = set(users_set)
                next_users.add(uid)
            if rec(col_idx, count_left - 1, next_users):
                result = True
                horas_mut[uid] += hpg
                if is_tut:
                    tut_mut.discard(uid)
                break
            horas_mut[uid] += hpg
            if is_tut:
                tut_mut.discard(uid)

        cache[key] = result
        return result

    return rec(0)


def _slots_desde_grupos(
    carga_cols: dict[int, dict],
    grupos_rest: dict[int, int],
) -> list[tuple[Decimal, bool]]:
    slots: list[tuple[Decimal, bool]] = []
    for cid, h, tut, n, _ in _columnas_desde_grupos(carga_cols, grupos_rest):
        for _ in range(n):
            slots.append((h, tut))
    return slots


def evaluar_eleccion_reparto(
    *,
    user_id: int,
    col_tipo: str,
    col_id: int,
    horas_map: dict[int, Decimal],
    grupos_rest_carga: dict[int, int],
    carga_cols: dict[int, dict],
    grupos_rest_otros: dict[int, int],
    otros_cols: dict[int, dict],
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    carga_counts_user: dict[tuple[int, int], int] | None = None,
    dist_init: dict[int, frozenset[int]] | None = None,
    memo: dict | None = None,
) -> str:
    """Evalúa viabilidad de asignar un grupo en carga docente u Otros."""
    uid = int(user_id)
    cid = int(col_id)
    horas_user = horas_map.get(uid, Decimal(0))
    dist_base = dist_init if dist_init is not None else distintos_por_carga(
        carga_counts_user or {}
    )

    if col_tipo == "carga":
        col = carga_cols.get(cid)
        if not col:
            return "rojo"
        rest = int(grupos_rest_carga.get(cid, 0))
        if rest <= 0:
            return "rojo"
        hpg = _dec(col.get("horas"))
        if hpg <= 0 or horas_user < hpg:
            return "rojo"
        is_tut = bool(col.get("tutoria"))
        if is_tut and (no_tutor.get(uid, False) or uid in tutoria_ya):
            return "rojo"
        min_d = _min_distinct(col)
        users_col = set(dist_base.get(cid, frozenset()))
        users_after = len(users_col) if uid in users_col else len(users_col) + 1
        if max(0, min_d - users_after) > rest - 1:
            return "rojo"
        horas_sim = dict(horas_map)
        horas_sim[uid] = horas_user - hpg
        grupos_carga_sim = dict(grupos_rest_carga)
        grupos_carga_sim[cid] = rest - 1
        grupos_otros_sim = grupos_rest_otros
        tutoria_sim = set(tutoria_ya)
        if is_tut:
            tutoria_sim.add(uid)
        users_col.add(uid)
        dist_sim = dict(dist_base)
        dist_sim[cid] = frozenset(users_col)
    elif col_tipo == "otro":
        col = otros_cols.get(cid)
        if not col:
            return "rojo"
        rest = int(grupos_rest_otros.get(cid, 0))
        if rest <= 0:
            return "rojo"
        hpg = _dec(col.get("horas"))
        if hpg <= 0 or horas_user < hpg:
            return "rojo"
        horas_sim = dict(horas_map)
        horas_sim[uid] = horas_user - hpg
        grupos_carga_sim = grupos_rest_carga
        grupos_otros_sim = dict(grupos_rest_otros)
        grupos_otros_sim[cid] = rest - 1
        tutoria_sim = tutoria_ya
        dist_sim = dist_base
    else:
        return "rojo"

    cols = _columnas_reparto(
        carga_cols,
        grupos_carga_sim,
        otros_cols,
        grupos_otros_sim,
    )
    if _puede_completar_columnas(
        horas_sim,
        cols,
        no_tutor=no_tutor,
        tutoria_ya=tutoria_sim,
        distintos_inicial=dist_sim,
        memo=memo,
    ):
        return "verde"
    return "rojo"


def evaluar_eleccion_carga(
    *,
    user_id: int,
    carga_id: int,
    horas_map: dict[int, Decimal],
    grupos_rest: dict[int, int],
    carga_cols: dict[int, dict],
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    carga_counts_user: dict[tuple[int, int], int] | None = None,
    otros_cols: dict[int, dict] | None = None,
    grupos_rest_otros: dict[int, int] | None = None,
    dist_init: dict[int, frozenset[int]] | None = None,
    memo: dict | None = None,
) -> str | None:
    """Devuelve 'verde' si la elección es viable, 'rojo' si no."""
    return evaluar_eleccion_reparto(
        user_id=user_id,
        col_tipo="carga",
        col_id=carga_id,
        horas_map=horas_map,
        grupos_rest_carga=grupos_rest,
        carga_cols=carga_cols,
        grupos_rest_otros=grupos_rest_otros or {},
        otros_cols=otros_cols or {},
        no_tutor=no_tutor,
        tutoria_ya=tutoria_ya,
        carga_counts_user=carga_counts_user,
        dist_init=dist_init,
        memo=memo,
    )


def evaluar_eleccion_otro(
    *,
    user_id: int,
    otro_id: int,
    horas_map: dict[int, Decimal],
    grupos_rest_carga: dict[int, int],
    carga_cols: dict[int, dict],
    grupos_rest_otros: dict[int, int],
    otros_cols: dict[int, dict],
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    carga_counts_user: dict[tuple[int, int], int] | None = None,
    dist_init: dict[int, frozenset[int]] | None = None,
    memo: dict | None = None,
) -> str | None:
    """Devuelve 'verde' si asignar un grupo Otros es viable, 'rojo' si no."""
    return evaluar_eleccion_reparto(
        user_id=user_id,
        col_tipo="otro",
        col_id=otro_id,
        horas_map=horas_map,
        grupos_rest_carga=grupos_rest_carga,
        carga_cols=carga_cols,
        grupos_rest_otros=grupos_rest_otros,
        otros_cols=otros_cols,
        no_tutor=no_tutor,
        tutoria_ya=tutoria_ya,
        carga_counts_user=carga_counts_user,
        dist_init=dist_init,
        memo=memo,
    )


def evaluar_bordes_reparto_turno(
    *,
    user_id: int,
    horas_map: dict[int, Decimal],
    grupos_rest_carga: dict[int, int],
    carga_cols: dict[int, dict],
    grupos_rest_otros: dict[int, int],
    otros_cols: dict[int, dict],
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    carga_ids: list[int],
    otro_ids: list[int],
    carga_counts_user: dict[tuple[int, int], int] | None = None,
    dist_init: dict[int, frozenset[int]] | None = None,
    global_viable: bool | None = None,
    memo: dict | None = None,
) -> tuple[dict[int, str], dict[int, str]]:
    """Evalúa bordes de carga docente y Otros en un solo paso con memo compartido."""
    uid = int(user_id)
    horas_user = horas_map.get(uid, Decimal(0))
    bordes_carga: dict[int, str] = {}
    bordes_otro: dict[int, str] = {}
    dist = dist_init if dist_init is not None else distintos_por_carga(
        carga_counts_user or {}
    )
    cache = memo if memo is not None else {}

    if global_viable is False:
        for cid in carga_ids:
            bordes_carga[int(cid)] = "rojo"
        for oid in otro_ids:
            bordes_otro[int(oid)] = "rojo"
        return bordes_carga, bordes_otro

    for oid in otro_ids:
        oid = int(oid)
        rest = int(grupos_rest_otros.get(oid, 0))
        if rest <= 0:
            bordes_otro[oid] = "rojo"
            continue
        col = otros_cols.get(oid)
        if not col:
            bordes_otro[oid] = "rojo"
            continue
        hpg = _dec(col.get("horas"))
        if hpg <= 0 or horas_user < hpg:
            bordes_otro[oid] = "rojo"
            continue
        bordes_otro[oid] = evaluar_eleccion_reparto(
            user_id=uid,
            col_tipo="otro",
            col_id=oid,
            horas_map=horas_map,
            grupos_rest_carga=grupos_rest_carga,
            carga_cols=carga_cols,
            grupos_rest_otros=grupos_rest_otros,
            otros_cols=otros_cols,
            no_tutor=no_tutor,
            tutoria_ya=tutoria_ya,
            carga_counts_user=carga_counts_user,
            dist_init=dist,
            memo=cache,
        )

    for cid in carga_ids:
        cid = int(cid)
        rest = int(grupos_rest_carga.get(cid, 0))
        if rest <= 0:
            bordes_carga[cid] = "rojo"
            continue
        col = carga_cols.get(cid)
        if not col:
            bordes_carga[cid] = "rojo"
            continue
        hpg = _dec(col.get("horas"))
        if hpg <= 0 or horas_user < hpg:
            bordes_carga[cid] = "rojo"
            continue
        if bool(col.get("tutoria")) and (
            no_tutor.get(uid, False) or uid in tutoria_ya
        ):
            bordes_carga[cid] = "rojo"
            continue
        bordes_carga[cid] = evaluar_eleccion_reparto(
            user_id=uid,
            col_tipo="carga",
            col_id=cid,
            horas_map=horas_map,
            grupos_rest_carga=grupos_rest_carga,
            carga_cols=carga_cols,
            grupos_rest_otros=grupos_rest_otros,
            otros_cols=otros_cols,
            no_tutor=no_tutor,
            tutoria_ya=tutoria_ya,
            carga_counts_user=carga_counts_user,
            dist_init=dist,
            memo=cache,
        )

    return bordes_carga, bordes_otro


def evaluar_bordes_otro_departamento(
    *,
    horas_map: dict[int, Decimal],
    grupos_rest_carga: dict[int, int],
    carga_cols: dict[int, dict],
    grupos_rest_otros: dict[int, int],
    otros_cols: dict[int, dict],
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    asignaciones: dict[int, list[int]],
    carga_counts_user: dict[tuple[int, int], int] | None = None,
    dist_init: dict[int, frozenset[int]] | None = None,
    global_viable: bool | None = None,
    memo: dict | None = None,
) -> dict[int, dict[int, str]]:
    """Evalúa bordes Otros para varios profesores con memo compartido."""
    out: dict[int, dict[int, str]] = {}
    if not asignaciones:
        return out

    dist = dist_init if dist_init is not None else distintos_por_carga(
        carga_counts_user or {}
    )
    cache = memo if memo is not None else {}
    viable = global_viable
    if viable is None:
        cols_global = _columnas_reparto(
            carga_cols,
            grupos_rest_carga,
            otros_cols,
            grupos_rest_otros,
        )
        viable = _puede_completar_columnas(
            dict(horas_map),
            cols_global,
            no_tutor=no_tutor,
            tutoria_ya=tutoria_ya,
            distintos_inicial=dist,
            memo=cache,
        )

    if not viable:
        for uid, oids in asignaciones.items():
            out[int(uid)] = {int(oid): "rojo" for oid in oids}
        return out

    for uid, oids in asignaciones.items():
        uid = int(uid)
        horas_user = horas_map.get(uid, Decimal(0))
        user_out: dict[int, str] = {}
        for oid in oids:
            oid = int(oid)
            rest = int(grupos_rest_otros.get(oid, 0))
            if rest <= 0:
                user_out[oid] = "rojo"
                continue
            col = otros_cols.get(oid)
            if not col:
                user_out[oid] = "rojo"
                continue
            hpg = _dec(col.get("horas"))
            if hpg <= 0 or horas_user < hpg:
                user_out[oid] = "rojo"
                continue
            borde = evaluar_eleccion_otro(
                user_id=uid,
                otro_id=oid,
                horas_map=horas_map,
                grupos_rest_carga=grupos_rest_carga,
                carga_cols=carga_cols,
                grupos_rest_otros=grupos_rest_otros,
                otros_cols=otros_cols,
                no_tutor=no_tutor,
                tutoria_ya=tutoria_ya,
                carga_counts_user=carga_counts_user,
                memo=cache,
            )
            user_out[oid] = borde or "rojo"
        out[uid] = user_out
    return out


def evaluar_bordes_otro_turno(
    *,
    user_id: int,
    horas_map: dict[int, Decimal],
    grupos_rest_carga: dict[int, int],
    carga_cols: dict[int, dict],
    grupos_rest_otros: dict[int, int],
    otros_cols: dict[int, dict],
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    otro_ids: list[int],
    carga_counts_user: dict[tuple[int, int], int] | None = None,
    dist_init: dict[int, frozenset[int]] | None = None,
    global_viable: bool | None = None,
    memo: dict | None = None,
) -> dict[int, str]:
    """Evalúa viabilidad de columnas Otros para el profesor con turno."""
    _, bordes_otro = evaluar_bordes_reparto_turno(
        user_id=user_id,
        horas_map=horas_map,
        grupos_rest_carga=grupos_rest_carga,
        carga_cols=carga_cols,
        grupos_rest_otros=grupos_rest_otros,
        otros_cols=otros_cols,
        no_tutor=no_tutor,
        tutoria_ya=tutoria_ya,
        carga_ids=[],
        otro_ids=otro_ids,
        carga_counts_user=carga_counts_user,
        dist_init=dist_init,
        global_viable=global_viable,
        memo=memo,
    )
    return bordes_otro


def evaluar_bordes_carga_turno(
    *,
    user_id: int,
    horas_map: dict[int, Decimal],
    grupos_rest: dict[int, int],
    carga_cols: dict[int, dict],
    no_tutor: dict[int, bool],
    tutoria_ya: set[int],
    carga_ids: list[int],
    carga_counts_user: dict[tuple[int, int], int] | None = None,
    otros_cols: dict[int, dict] | None = None,
    grupos_rest_otros: dict[int, int] | None = None,
    dist_init: dict[int, frozenset[int]] | None = None,
    global_viable: bool | None = None,
    memo: dict | None = None,
) -> dict[int, str]:
    """Evalúa viabilidad de varias columnas con memoización compartida."""
    bordes_carga, _ = evaluar_bordes_reparto_turno(
        user_id=user_id,
        horas_map=horas_map,
        grupos_rest_carga=grupos_rest,
        carga_cols=carga_cols,
        grupos_rest_otros=grupos_rest_otros or {},
        otros_cols=otros_cols or {},
        no_tutor=no_tutor,
        tutoria_ya=tutoria_ya,
        carga_ids=carga_ids,
        otro_ids=[],
        carga_counts_user=carga_counts_user,
        dist_init=dist_init,
        global_viable=global_viable,
        memo=memo,
    )
    return bordes_carga
