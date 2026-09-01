"""Configuración del reparto por departamento (modo de elección y turno)."""

from __future__ import annotations

from db.connection import get_db
from db.reparto_miembros import (
    TIPO_FUNCIONARIO_DESTINO,
    TIPO_INTERINO,
    TIPO_OTRO_FUNCIONARIO,
)

TABLE = "reparto_repartir_config"
_schema_ready = False

MODO_RONDA_TODOS = "ronda_todos"
MODO_RONDA_CATEGORIAS = "ronda_categorias"
MODO_UNO_COMPLETO = "uno_completo"

MODOS_ELECCION: tuple[tuple[str, str], ...] = (
    (MODO_RONDA_TODOS, "Todos los miembros eligen en ronda"),
    (MODO_RONDA_CATEGORIAS, "Rondas por categorías (1º Destino, 2º Otros funcionarios, 3º Interinos)"),
    (MODO_UNO_COMPLETO, "Rellenar el horario de uno en uno"),
)
MODOS_IDS = frozenset(m[0] for m in MODOS_ELECCION)


def _categoria_rank(tipo: str | None) -> int:
    t = (tipo or "").strip()
    if t == TIPO_INTERINO:
        return 2
    if t == TIPO_FUNCIONARIO_DESTINO:
        return 0
    return 1


def _horas_restantes(fila: dict) -> int:
    raw = str(fila.get("horas") or "").strip().replace(",", ".")
    if not raw:
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def _ordenados_con_horas(filas: list[dict]) -> list[dict]:
    activos = [f for f in filas if _horas_restantes(f) > 0]
    return sorted(activos, key=lambda f: (int(f.get("orden") or 0), str(f.get("nombre") or "")))


def _siguiente_activo_tras_picker(
    filas: list[dict],
    picker_uid: int,
    activos: list[dict],
) -> int | None:
    """
    Siguiente turno entre quienes tienen horas.
    Si el que eligió sigue activo, pasa al siguiente en la ronda.
    Si terminó (0 h), pasa al siguiente en orden de fila, no al primero de la lista.
    """
    if not activos:
        return None
    picker = int(picker_uid)
    ids = [int(f["user_id"]) for f in activos]
    if picker in ids:
        idx = ids.index(picker)
        return ids[(idx + 1) % len(ids)]
    picker_fila = next((f for f in filas if int(f["user_id"]) == picker), None)
    picker_orden = int(picker_fila.get("orden") or 0) if picker_fila else 0
    candidatos = [f for f in activos if int(f.get("orden") or 0) > picker_orden]
    if candidatos:
        return int(candidatos[0]["user_id"])
    return int(activos[0]["user_id"])


def _ordenados_categoria(filas: list[dict], categoria_rank: int) -> list[dict]:
    return [
        f
        for f in _ordenados_con_horas(filas)
        if _categoria_rank(str(f.get("tipo") or "")) == categoria_rank
    ]


def _categoria_activa(filas: list[dict]) -> int | None:
    for rank in (0, 1, 2):
        if _ordenados_categoria(filas, rank):
            return rank
    return None


def turno_inicial(modo: str, filas: list[dict]) -> int | None:
    modo_n = modo if modo in MODOS_IDS else MODO_RONDA_TODOS
    if modo_n == MODO_RONDA_CATEGORIAS:
        rank = _categoria_activa(filas)
        if rank is None:
            return None
        cat = _ordenados_categoria(filas, rank)
        return int(cat[0]["user_id"]) if cat else None
    activos = _ordenados_con_horas(filas)
    return int(activos[0]["user_id"]) if activos else None


def siguiente_turno(modo: str, filas: list[dict], picker_uid: int) -> int | None:
    modo_n = modo if modo in MODOS_IDS else MODO_RONDA_TODOS
    picker = int(picker_uid)
    if modo_n == MODO_UNO_COMPLETO:
        fila = next((f for f in filas if int(f["user_id"]) == picker), None)
        if fila and _horas_restantes(fila) > 0:
            return picker
        activos = _ordenados_con_horas(filas)
        return _siguiente_activo_tras_picker(filas, picker, activos)
    if modo_n == MODO_RONDA_CATEGORIAS:
        rank = _categoria_activa(filas)
        if rank is None:
            return None
        cat = _ordenados_categoria(filas, rank)
        if not cat:
            return turno_inicial(modo_n, filas)
        return _siguiente_activo_tras_picker(filas, picker, cat)
    activos = _ordenados_con_horas(filas)
    return _siguiente_activo_tras_picker(filas, picker, activos)


def saltar_turno(modo: str, filas: list[dict], turno_uid: int) -> int | None:
    """
    Pasa al siguiente con horas sin elegir (salto voluntario).
    En modo uno completo no se queda en el mismo profesor.
    """
    modo_n = modo if modo in MODOS_IDS else MODO_RONDA_TODOS
    picker = int(turno_uid)
    if modo_n == MODO_RONDA_CATEGORIAS:
        rank = _categoria_activa(filas)
        if rank is None:
            return None
        cat = _ordenados_categoria(filas, rank)
        if not cat:
            return turno_inicial(modo_n, filas)
        return _siguiente_activo_tras_picker(filas, picker, cat)
    activos = _ordenados_con_horas(filas)
    if not activos:
        return None
    return _siguiente_activo_tras_picker(filas, picker, activos)


def get_repartir_config(departamento_abrev: str) -> dict:
    ensure_reparto_repartir_config_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return {"modo_eleccion": MODO_RONDA_TODOS, "turno_user_id": None}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT modo_eleccion, turno_user_id
                FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (key,),
            )
            row = cur.fetchone()
    if not row:
        return {"modo_eleccion": MODO_RONDA_TODOS, "turno_user_id": None}
    tid = row.get("turno_user_id")
    modo = str(row.get("modo_eleccion") or MODO_RONDA_TODOS).strip()
    if modo not in MODOS_IDS:
        modo = MODO_RONDA_TODOS
    return {
        "modo_eleccion": modo,
        "turno_user_id": int(tid) if tid is not None else None,
    }


def set_modo_eleccion(
    *,
    departamento_abrev: str,
    modo_eleccion: str,
    filas: list[dict],
) -> None:
    ensure_reparto_repartir_config_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        raise ValueError("Departamento obligatorio")
    modo = modo_eleccion if modo_eleccion in MODOS_IDS else MODO_RONDA_TODOS
    turno = turno_inicial(modo, filas)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (departamento_abrev, modo_eleccion, turno_user_id, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (departamento_abrev) DO UPDATE
                SET modo_eleccion = EXCLUDED.modo_eleccion,
                    turno_user_id = EXCLUDED.turno_user_id,
                    updated_at = now()
                """,
                (key, modo, turno),
            )


def sync_turno(
    *,
    departamento_abrev: str,
    modo_eleccion: str,
    filas: list[dict],
    turno_guardado: int | None = None,
) -> int | None:
    """Asegura turno válido; devuelve user_id con turno."""
    ensure_reparto_repartir_config_schema()
    key = (departamento_abrev or "").strip()
    modo = modo_eleccion if modo_eleccion in MODOS_IDS else MODO_RONDA_TODOS
    turno = turno_guardado
    if turno is None:
        cfg = get_repartir_config(key)
        turno = cfg.get("turno_user_id")
    ids_activos = {int(f["user_id"]) for f in filas if _horas_restantes(f) > 0}
    if turno is None or turno not in ids_activos:
        activos = _ordenados_con_horas(filas)
        if turno is not None and turno not in ids_activos:
            if modo == MODO_RONDA_CATEGORIAS:
                rank = _categoria_activa(filas)
                cat = _ordenados_categoria(filas, rank) if rank is not None else []
                turno_sig = _siguiente_activo_tras_picker(filas, turno, cat) if cat else None
            else:
                turno_sig = _siguiente_activo_tras_picker(filas, turno, activos)
            turno = turno_sig if turno_sig is not None else turno_inicial(modo, filas)
        else:
            turno = turno_inicial(modo, filas)
    if modo == MODO_RONDA_CATEGORIAS and turno is not None:
        rank = _categoria_activa(filas)
        if rank is not None:
            cat_ids = {int(f["user_id"]) for f in _ordenados_categoria(filas, rank)}
            if turno not in cat_ids:
                turno = turno_inicial(modo, filas)
    cfg = get_repartir_config(key)
    guardado = turno_guardado if turno_guardado is not None else cfg.get("turno_user_id")
    if turno == guardado and modo == cfg.get("modo_eleccion"):
        return turno
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (departamento_abrev, modo_eleccion, turno_user_id, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (departamento_abrev) DO UPDATE
                SET turno_user_id = EXCLUDED.turno_user_id,
                    updated_at = now()
                """,
                (key, modo, turno),
            )
    return turno


def iniciar_turno_reparto(
    *,
    departamento_abrev: str,
    modo_eleccion: str,
    filas: list[dict],
) -> int | None:
    """Al cerrar las horas nominales, el turno pasa al primer miembro (orden 1)."""
    ensure_reparto_repartir_config_schema()
    key = (departamento_abrev or "").strip()
    modo = modo_eleccion if modo_eleccion in MODOS_IDS else MODO_RONDA_TODOS
    turno = turno_inicial(modo, filas)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (departamento_abrev, modo_eleccion, turno_user_id, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (departamento_abrev) DO UPDATE
                SET turno_user_id = EXCLUDED.turno_user_id,
                    updated_at = now()
                """,
                (key, modo, turno),
            )
    return turno


def advance_turno_after_pick(
    *,
    departamento_abrev: str,
    picker_user_id: int,
    filas: list[dict],
    modo_eleccion: str | None = None,
) -> None:
    ensure_reparto_repartir_config_schema()
    key = (departamento_abrev or "").strip()
    if modo_eleccion is not None:
        modo = modo_eleccion if modo_eleccion in MODOS_IDS else MODO_RONDA_TODOS
    else:
        cfg = get_repartir_config(key)
        modo = cfg["modo_eleccion"]
    nuevo = siguiente_turno(modo, filas, int(picker_user_id))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET turno_user_id = %s, updated_at = now()
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (nuevo, key),
            )


def set_turno_user_id(
    departamento_abrev: str,
    turno_user_id: int | None,
) -> None:
    ensure_reparto_repartir_config_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET turno_user_id = %s, updated_at = now()
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (turno_user_id, key),
            )


def saltar_turno_reparto(
    *,
    departamento_abrev: str,
    filas: list[dict],
    modo_eleccion: str | None = None,
) -> int | None:
    """Avanza el turno sin asignación (profesor salta voluntariamente)."""
    ensure_reparto_repartir_config_schema()
    from db.reparto_pasos import ensure_reparto_pasos_schema, TIPO_SALTAR

    ensure_reparto_pasos_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return None
    cfg = get_repartir_config(key)
    turno = cfg.get("turno_user_id")
    if turno is None:
        return None
    turno_ant = int(turno)
    modo = modo_eleccion if modo_eleccion in MODOS_IDS else cfg["modo_eleccion"]
    nuevo = saltar_turno(modo, filas, turno_ant)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reparto_pasos
                    (departamento_abrev, tipo, registro_id, turno_user_id)
                VALUES (%s, %s, NULL, %s)
                """,
                (key, TIPO_SALTAR, turno_ant),
            )
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET turno_user_id = %s, updated_at = now()
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (nuevo, key),
            )
    return nuevo


def puede_elegir(
    *,
    user_id: int,
    turno_user_id: int | None,
    filas: list[dict],
    modo_eleccion: str,
) -> bool:
    if turno_user_id is None:
        return False
    if int(user_id) != int(turno_user_id):
        return False
    fila = next((f for f in filas if int(f["user_id"]) == int(user_id)), None)
    if not fila or _horas_restantes(fila) <= 0:
        return False
    if modo_eleccion == MODO_RONDA_CATEGORIAS:
        rank = _categoria_activa(filas)
        if rank is None:
            return False
        return _categoria_rank(str(fila.get("tipo") or "")) == rank
    return True


def ensure_reparto_repartir_config_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    departamento_abrev TEXT PRIMARY KEY,
                    modo_eleccion TEXT NOT NULL DEFAULT '{MODO_RONDA_TODOS}',
                    turno_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
    _schema_ready = True
