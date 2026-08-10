from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok"}


# Feature routers are mounted here as they are built:
#   from app.api.routes import auth, conversations, kb, webhooks
#   api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
