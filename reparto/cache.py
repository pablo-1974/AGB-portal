"""Caché en memoria para estructura estática del reparto (no asignaciones)."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from db.reparto_catalog_materia_depto import get_catalog_materia_depto_map

_catalog_map_cache: dict[str, str] | None = None
_bloques_cache: dict[str, tuple[str, list]] = {}
_snapshot_cache: dict[str, Any] = {}
_viabilidad_cache: dict[tuple[str, str], tuple[bool, dict[int, str], dict[int, str]]] = {}


def catalog_depto_map() -> dict[str, str]:
    global _catalog_map_cache
    if _catalog_map_cache is None:
        _catalog_map_cache = get_catalog_materia_depto_map()
    return _catalog_map_cache


def bloques_fingerprint(
    nominales: list[dict],
    carga_items: list[dict],
    otros_items: list[dict],
) -> str:
    parts: list[str] = []
    for n in nominales:
        parts.append(f"n:{n['id']}")
    for c in carga_items:
        parts.append(
            f"c:{c['id']}:{c.get('curso_key')}:{c.get('materia_abrev')}:"
            f"{c.get('grupos')}:{c.get('horas_por_grupo')}:{c.get('tutoria')}:{c.get('dc')}"
        )
    for o in otros_items:
        parts.append(f"o:{o['id']}")
    return "|".join(parts)


def get_cached_bloques(
    abreviatura: str,
    fingerprint: str,
    builder: Callable[[], list],
) -> list[dict]:
    key = (abreviatura or "").strip().lower()
    cached = _bloques_cache.get(key)
    if cached and cached[0] == fingerprint:
        return cached[1]
    bloques = builder()
    _bloques_cache[key] = (fingerprint, bloques)
    return bloques


def clear_reparto_structure_cache(abreviatura: str | None = None) -> None:
    global _catalog_map_cache
    if abreviatura:
        key = abreviatura.strip().lower()
        _bloques_cache.pop(key, None)
        invalidate_departamento_runtime_cache(key)
    else:
        _bloques_cache.clear()
        _catalog_map_cache = None
        clear_reparto_runtime_cache()


def invalidate_departamento_runtime_cache(abreviatura: str) -> None:
    """Tras mutar asignaciones o turno: invalida snapshot y viabilidad del departamento."""
    key = (abreviatura or "").strip().lower()
    if not key:
        return
    _snapshot_cache.pop(key, None)
    for cache_key in list(_viabilidad_cache.keys()):
        if cache_key[0] == key:
            _viabilidad_cache.pop(cache_key, None)


def clear_reparto_runtime_cache() -> None:
    _snapshot_cache.clear()
    _viabilidad_cache.clear()


def get_cached_snapshot(abreviatura: str) -> Any | None:
    key = (abreviatura or "").strip().lower()
    return _snapshot_cache.get(key)


def set_cached_snapshot(abreviatura: str, snap: Any) -> None:
    key = (abreviatura or "").strip().lower()
    if key:
        _snapshot_cache[key] = snap


def viabilidad_fingerprint(
    *,
    turno_user_id: int | None,
    horas_map: dict[int, Decimal],
    grupos_rest_carga: dict[int, int],
    grupos_rest_otros: dict[int, int],
    carga_counts_user: dict[tuple[int, int], int],
) -> str:
    parts: list[str] = [f"t:{turno_user_id}"]
    for uid, h in sorted(horas_map.items()):
        parts.append(f"h:{uid}:{h}")
    for cid, n in sorted(grupos_rest_carga.items()):
        parts.append(f"cr:{cid}:{n}")
    for oid, n in sorted(grupos_rest_otros.items()):
        parts.append(f"or:{oid}:{n}")
    for (cid, uid), n in sorted(carga_counts_user.items()):
        parts.append(f"cu:{cid}:{uid}:{n}")
    return "|".join(parts)


def get_cached_viabilidad_bordes(
    abreviatura: str,
    fingerprint: str,
) -> tuple[bool, dict[int, str], dict[int, str]] | None:
    key = ((abreviatura or "").strip().lower(), fingerprint)
    return _viabilidad_cache.get(key)


def set_cached_viabilidad_bordes(
    abreviatura: str,
    fingerprint: str,
    global_viable: bool,
    bordes_carga: dict[int, str],
    bordes_otro: dict[int, str],
) -> None:
    abr = (abreviatura or "").strip().lower()
    if not abr:
        return
    _viabilidad_cache[(abr, fingerprint)] = (
        global_viable,
        dict(bordes_carga),
        dict(bordes_otro),
    )
