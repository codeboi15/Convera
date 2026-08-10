from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, conversations, team, widget

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

# Feature routers are mounted here as they are built:
#   from app.api.routes import kb, webhooks
