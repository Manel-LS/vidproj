from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    ai,
    auth,
    catalog,
    characters,
    files,
    jobs,
    media,
    projects,
    renders,
    scenes,
    templates,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(catalog.router)
api_router.include_router(characters.router)
api_router.include_router(projects.router)
api_router.include_router(media.router)
api_router.include_router(scenes.router)
api_router.include_router(templates.router)
api_router.include_router(ai.router)
api_router.include_router(jobs.router)
api_router.include_router(renders.router)
api_router.include_router(files.router)
