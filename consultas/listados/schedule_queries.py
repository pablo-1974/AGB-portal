"""Consultas agregadas sobre ``schedule_slots`` para vistas grupo / aula / guardia."""



from __future__ import annotations



from collections import defaultdict

from typing import Any



from db.connection import get_db

from utils.text import normalize_for_sort





def list_distinct_class_groups_from_slots() -> list[str]:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT DISTINCT TRIM("group") AS g

                FROM schedule_slots

                WHERE type = 'CLASS'

                  AND "group" IS NOT NULL

                  AND TRIM("group") <> ''

                """

            )

            rows = cur.fetchall()

    names = sorted({str(r["g"]).strip() for r in rows if r.get("g")}, key=normalize_for_sort)

    return names





def list_distinct_class_rooms_from_slots() -> list[str]:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT DISTINCT TRIM(room) AS r

                FROM schedule_slots

                WHERE type = 'CLASS'

                  AND room IS NOT NULL

                  AND TRIM(room) <> ''

                """

            )

            rows = cur.fetchall()

    names = sorted({str(r["r"]).strip() for r in rows if r.get("r")}, key=normalize_for_sort)

    return names





def list_distinct_guard_types_from_slots() -> list[str]:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT DISTINCT TRIM(guard_type) AS gt

                FROM schedule_slots

                WHERE type = 'GUARD'

                  AND guard_type IS NOT NULL

                  AND TRIM(guard_type) <> ''

                """

            )

            rows = cur.fetchall()

    names = sorted({str(r["gt"]).strip() for r in rows if r.get("gt")}, key=normalize_for_sort)

    return names





def _norm_key(s: str) -> str:

    return " ".join((s or "").strip().lower().split())





def _teacher_display_sql() -> str:

    """Alias si existe; si no, nombre (misma expresión en todas las consultas de listados)."""

    return "COALESCE(NULLIF(TRIM(u.alias), ''), u.name)"





def fetch_class_slots_by_group(group_name: str) -> list[dict]:

    key = (group_name or "").strip()

    if not key:

        return []

    td = _teacher_display_sql()

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT s.day_index, s.hour_index, s.subject, s.room, s."group",

                       {td} AS teacher_display

                FROM schedule_slots s

                JOIN users u ON u.id = s.teacher_id

                WHERE s.type = 'CLASS'

                  AND TRIM(s."group") <> ''

                  AND LOWER(TRIM(s."group")) = LOWER(TRIM(%s))

                """,

                (key,),

            )

            return list(cur.fetchall())





def list_group_staff_for_pdf(group_name: str) -> list[dict[str, str]]:

    """Profesores con al menos una hora CLASS en el grupo: nombre y asignatura, orden alfabético."""

    key = (group_name or "").strip()

    if not key:

        return []

    td = _teacher_display_sql()

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT nombre, asignatura

                FROM (

                    SELECT DISTINCT

                           {td} AS nombre,

                           TRIM(COALESCE(s.subject, '')) AS asignatura

                    FROM schedule_slots s

                    JOIN users u ON u.id = s.teacher_id

                    WHERE s.type = 'CLASS'

                      AND TRIM(s."group") <> ''

                      AND LOWER(TRIM(s."group")) = LOWER(TRIM(%s))

                ) AS staff

                ORDER BY LOWER(nombre), LOWER(asignatura)

                """,

                (key,),

            )

            rows = cur.fetchall()

    return [

        {

            "nombre": str(r.get("nombre") or "").strip(),

            "asignatura": str(r.get("asignatura") or "").strip(),

        }

        for r in rows

        if str(r.get("nombre") or "").strip()

    ]





def fetch_class_slots_by_room(room_name: str) -> list[dict]:

    key = (room_name or "").strip()

    if not key:

        return []

    td = _teacher_display_sql()

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT s.day_index, s.hour_index, s.subject, s.room, s."group",

                       {td} AS teacher_display

                FROM schedule_slots s

                JOIN users u ON u.id = s.teacher_id

                WHERE s.type = 'CLASS'

                  AND TRIM(s.room) <> ''

                  AND LOWER(TRIM(s.room)) = LOWER(TRIM(%s))

                """,

                (key,),

            )

            return list(cur.fetchall())





def fetch_guard_slots_by_type(guard_type: str) -> list[dict]:

    key = (guard_type or "").strip()

    if not key:

        return []

    td = _teacher_display_sql()

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT s.day_index, s.hour_index, s.guard_type,

                       {td} AS teacher_display

                FROM schedule_slots s

                JOIN users u ON u.id = s.teacher_id

                WHERE s.type = 'GUARD'

                  AND TRIM(s.guard_type) <> ''

                  AND TRIM(s.guard_type) = %s

                """,

                (key,),

            )

            return list(cur.fetchall())





def fetch_all_guard_slots() -> list[dict]:

    """Todas las celdas de tipo GUARD con tipo no vacío."""

    td = _teacher_display_sql()

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT s.day_index, s.hour_index, s.guard_type,

                       {td} AS teacher_display

                FROM schedule_slots s

                JOIN users u ON u.id = s.teacher_id

                WHERE s.type = 'GUARD'

                  AND TRIM(COALESCE(s.guard_type, '')) <> ''

                """

            )

            return list(cur.fetchall())





def _teacher_label_row(r: dict) -> str:

    return str(r.get("teacher_display") or r.get("teacher_name") or "").strip()





def _aggregate_cell_lines(rows_at_cell: list[dict], *, mode: str) -> list[str]:

    out: list[str] = []

    for r in rows_at_cell:

        tlabel = _teacher_label_row(r)

        if mode == "group":

            subj = str(r.get("subject") or "").strip()

            room = str(r.get("room") or "").strip()

            bits = [tlabel]

            if subj:

                bits.append(subj)

            if room:

                bits.append(room)

            out.append(" · ".join(bits))

        elif mode == "room":

            grp = str(r.get("group") or "").strip()

            subj = str(r.get("subject") or "").strip()

            bits = [tlabel]

            if grp:

                bits.append(grp)

            if subj:

                bits.append(subj)

            out.append(" · ".join(bits))

        elif mode == "guard_all":

            gtype = str(r.get("guard_type") or "").strip()

            if tlabel and gtype:

                out.append(f"{tlabel} — {gtype}")

            elif tlabel:

                out.append(tlabel)

            elif gtype:

                out.append(gtype)

        else:  # guard (un solo tipo): solo alias, el tipo ya va en el filtro de la vista

            if tlabel:

                out.append(tlabel)

    return out





RECREO_HOUR_INDEX = 3





def _dedupe_preserve_order(labels: list[str]) -> list[str]:

    seen: set[str] = set()

    out: list[str] = []

    for x in labels:

        t = str(x).strip()

        if not t or t in seen:

            continue

        seen.add(t)

        out.append(t)

    return out





def _recreo_guard_zone(r: dict) -> str | None:

    """Clasifica guardia de recreo importada; None si no encaja en pasillo/patio."""

    g = str(r.get("guard_type") or "").strip().upper()

    if not g.startswith("G RECREO"):

        return None

    if "PASILLO" in g:

        return "pasillo"

    if "PATIO" in g:

        return "patio"

    return None





def build_guardias_matrix(rows: list[dict]) -> list[list[Any]]:

    """Vista «todas las guardias»: aula = solo alias; recreo = pasillo arriba y patio abajo."""

    bucket: dict[tuple[int, int], list[dict]] = defaultdict(list)

    for r in rows:

        try:

            di = int(r["day_index"])

            hi = int(r["hour_index"])

        except (TypeError, ValueError, KeyError):

            continue

        if 0 <= di <= 4 and 0 <= hi <= 6:

            bucket[(hi, di)].append(r)



    matrix: list[list[Any]] = [[None for _ in range(5)] for _ in range(7)]

    for (hi, di), lst in bucket.items():

        if hi == RECREO_HOUR_INDEX:

            pas: list[str] = []

            pat: list[str] = []

            other: list[str] = []

            for r in lst:

                lab = _teacher_label_row(r)

                if not lab:

                    continue

                zone = _recreo_guard_zone(r)

                if zone == "pasillo":

                    pas.append(lab)

                elif zone == "patio":

                    pat.append(lab)

                else:

                    other.append(lab)

            if other:

                pas.extend(other)

            pas = _dedupe_preserve_order(pas)

            pat = _dedupe_preserve_order(pat)

            if pas or pat:

                matrix[hi][di] = {

                    "schedule_kind": "GUARD_RECREO",

                    "pasillo": pas,

                    "patio": pat,

                }

        else:

            aliases: list[str] = []

            for r in lst:

                lab = _teacher_label_row(r)

                if lab:

                    aliases.append(lab)

            aliases = _dedupe_preserve_order(aliases)

            if aliases:

                matrix[hi][di] = {

                    "schedule_kind": "GUARD_AULA_ALIASES",

                    "aliases": aliases,

                }

    return matrix





def build_aggregate_matrix(rows: list[dict], *, mode: str) -> list[list[Any]]:

    """Celdas ``{schedule_kind: 'BLOQUE', lines: [...]}`` o ``None``."""

    bucket: dict[tuple[int, int], list[dict]] = defaultdict(list)

    for r in rows:

        try:

            di = int(r["day_index"])

            hi = int(r["hour_index"])

        except (TypeError, ValueError, KeyError):

            continue

        if 0 <= di <= 4 and 0 <= hi <= 6:

            bucket[(hi, di)].append(r)



    matrix: list[list[Any]] = [[None for _ in range(5)] for _ in range(7)]

    for (hi, di), lst in bucket.items():

        lines = _aggregate_cell_lines(lst, mode=mode)

        if lines:

            matrix[hi][di] = {"schedule_kind": "BLOQUE", "lines": lines}

    return matrix

