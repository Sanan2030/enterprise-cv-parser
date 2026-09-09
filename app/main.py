import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.routes import dashboard_router, router
from app.core.config import settings
from app.core.logging import configure_logging


class BodyLimitMiddleware:
    """Bound streamed body before multipart allocation, including missing/false length."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 64 * 1024
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                return await JSONResponse(
                    {"detail": "Request body exceeds the upload limit."}, status_code=413
                )(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    app.state.parse_slots = asyncio.Semaphore(settings.MAX_CONCURRENT_PARSES)
    yield


app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware)
app.include_router(router, prefix=settings.API_V1_STR)

app.include_router(dashboard_router)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
)


@app.get("/", response_class=FileResponse, include_in_schema=False)
@app.get("/index.html", response_class=FileResponse, include_in_schema=False)
async def dashboard() -> FileResponse:
    source = Path(__file__).resolve().parents[1] / "index.html"
    if not source.exists():
        source = Path(sys.prefix) / "share" / "enterprise-cv-parser" / "index.html"
    return FileResponse(source, media_type="text/html", headers={"Cache-Control": "no-cache"})
