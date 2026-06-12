"""Agregador de routers de buzones (apps independientes)."""

from __future__ import annotations

from fastapi import APIRouter

from buzones.funcionamiento_portal.router import router as funcionamiento_portal_router
from buzones.listados.router import router as listados_buzon_router
from buzones.mantenimiento.router import router as mantenimiento_router

router = APIRouter(tags=["buzones"])
router.include_router(funcionamiento_portal_router)
router.include_router(mantenimiento_router)
router.include_router(listados_buzon_router)
