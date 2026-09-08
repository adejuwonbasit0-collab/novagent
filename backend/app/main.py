from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    admin,
    assistant,
    auth,
    conversations,
    devices,
    health as health_api,
    knowledge,
    permissions,
    reminders,
    security,
    settings as settings_api,
    speaker,
    tools,
    voice,
    ws,
)
from app.core.config import settings
from app.services.connection_manager import connection_manager

# Importing this module registers its tools with ToolRegistry as a side effect.
import app.tools.reminder_tools  # noqa: F401
import app.tools.system_tools  # noqa: F401
import app.tools.os_file_tools  # noqa: F401
import app.tools.knowledge_tools  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: DB tables are managed via Alembic migrations, not created here —
    # keeps schema changes explicit and reviewable (see alembic/).
    #
    # connection_manager.start() connects to Redis and begins listening for
    # commands/results forwarded from other backend instances. If Redis is
    # unreachable it logs a warning and falls back to single-instance mode
    # automatically — this call is safe even in local dev with no Redis
    # running, since the local WebSocket dispatch path doesn't need it.
    await connection_manager.start()
    yield
    await connection_manager.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.2.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(devices.router)
app.include_router(permissions.router)
app.include_router(reminders.router)
app.include_router(knowledge.router)
app.include_router(voice.router)
app.include_router(speaker.router)
app.include_router(settings_api.router)
app.include_router(tools.router)
app.include_router(assistant.router)
app.include_router(ws.router)
app.include_router(security.router)
app.include_router(health_api.router)
app.include_router(conversations.router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "environment": settings.ENVIRONMENT}
