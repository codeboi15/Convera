from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    auth,
    conversations,
    domains,
    kb,
    public_kb,
    team,
    webhooks,
    widget,
    workspace,
)

api_router = APIRouter()


@api_router.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok"}


api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(team.router, prefix="/team", tags=["team"])
api_router.include_router(
    conversations.router, prefix="/conversations", tags=["conversations"]
)
api_router.include_router(widget.router, prefix="/widget", tags=["widget"])
api_router.include_router(
    workspace.router, prefix="/workspace", tags=["workspace"]
)
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(kb.router, prefix="/kb", tags=["knowledge-base"])
api_router.include_router(domains.router, prefix="/domains", tags=["custom-domains"])
api_router.include_router(
    domains.public_router, prefix="/public/domains", tags=["custom-domains"]
)
# Public, unauthenticated: help centre pages and widget article suggestions.
api_router.include_router(
    public_kb.router, prefix="/public/kb", tags=["public-kb"]
)
