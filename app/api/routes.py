import asyncio
import hmac
import json
import os
import signal
import sys
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.core.logging import logger
from app.schemas.dashboard import DashboardResponse
from app.schemas.resume import ResumeParsedSchema

router = APIRouter()
dashboard_router = APIRouter()
UPLOAD_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            }
        },
    }
}


async def stop_worker(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return
        await process.wait()


@router.post("/resume/parse", response_model=ResumeParsedSchema, openapi_extra=UPLOAD_SCHEMA)
async def parse_resume_endpoint(request: Request) -> ResumeParsedSchema:
    return await process_document(request, dashboard=False)


@dashboard_router.post("/api/extract-cv", response_model=DashboardResponse, openapi_extra=UPLOAD_SCHEMA)
async def extract_cv_endpoint(request: Request) -> DashboardResponse:
    return await process_document(request, dashboard=True)


async def process_document(
    request: Request, dashboard: bool = False
) -> ResumeParsedSchema | DashboardResponse:
    if settings.API_KEY and not hmac.compare_digest(
        request.headers.get("x-api-key", ""), settings.API_KEY.get_secret_value()
    ):
        raise HTTPException(401, "Invalid API key.")
    semaphore = request.app.state.parse_slots
    if semaphore.locked():
        raise HTTPException(503, "Parser capacity reached; retry later.", headers={"Retry-After": "5"})
    async with semaphore:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        async with request.form(max_files=1, max_fields=0, max_part_size=1024) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile) or not file.filename:
                raise HTTPException(422, "A PDF file field is required.")
            if Path(file.filename).suffix.lower() != ".pdf":
                raise HTTPException(415, "Only PDF files are accepted.")
            if file.content_type not in {"application/pdf", "application/octet-stream"}:
                raise HTTPException(415, "Unsupported media type.")
            with tempfile.TemporaryDirectory(prefix="cv-parser-") as directory:
                source = Path(directory) / "input.pdf"
                destination = Path(directory) / "result.json"
                size = 0
                with source.open("wb") as stream:
                    while chunk := await file.read(64 * 1024):
                        size += len(chunk)
                        if size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                            raise HTTPException(413, "PDF exceeds the upload limit.")
                        stream.write(chunk)
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "app.services.worker",
                    str(source),
                    str(destination),
                    file.filename,
                    "dashboard" if dashboard else "native",
                    start_new_session=os.name == "posix",
                    env={**os.environ, "TMPDIR": directory, "TEMP": directory, "TMP": directory},
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    await asyncio.wait_for(process.wait(), settings.PARSE_TIMEOUT)
                    if process.returncode or not destination.exists():
                        raise HTTPException(500, "Document processing failed.")
                    payload = json.loads(destination.read_text(encoding="utf-8"))
                    if "error" in payload:
                        error = payload["error"]
                        raise HTTPException(
                            error["status"], {"code": error["code"], "message": error["message"]}
                        )
                    result = (DashboardResponse if dashboard else ResumeParsedSchema).model_validate(
                        payload["result"]
                    )
                except TimeoutError as exc:
                    raise HTTPException(504, "Document processing timed out.") from exc
                finally:
                    await stop_worker(process)
                logger.bind(
                    request_id=request_id,
                    pages=result.metadata.pages if dashboard else result.document.page_count,
                    elapsed_ms=round((time.perf_counter() - start) * 1000),
                ).info("parse_complete")
                return result


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "version": settings.VERSION}


@dashboard_router.get("/api/config")
async def dashboard_config() -> dict[str, bool | int]:
    return {
        "llmEnabled": settings.USE_LLM_FALLBACK,
        "apiKeyRequired": bool(settings.API_KEY),
        "maxUploadBytes": settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024,
    }
