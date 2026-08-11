from __future__ import annotations

from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.realtime.server import sio

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup/shutdown hooks (queue pool, warmups) are added here as needed.
    yield


app = FastAPI(title="InterCom API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Outermost middleware: every request gets an id before anything else runs,
# including the CORS layer, so even rejected requests are traceable.
app.add_middleware(RequestIdMiddleware)

app.include_router(api_router, prefix="/api")


@app.get("/", tags=["system"])
async def root() -> dict:
    return {"service": "intercom-api", "version": "0.1.0"}


# Combined ASGI app: Socket.IO (real-time) mounted alongside FastAPI (REST).
# Run with: uvicorn app.main:asgi
asgi = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="socket.io")
