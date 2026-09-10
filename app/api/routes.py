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
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.core.exceptions import CVParserException
from app.core.logging import logger
from app.schemas.dashboard import DashboardResponse
from app.schemas.job_match import JobMatchRequest, JobMatchResponse
from app.schemas.resume import ResumeParsedSchema
from app.services.dashboard_adapter import adapt_resume
from app.services.resume_parser import ResumeParserService

router = APIRouter()
dashboard_router = APIRouter()


def analyze_job(payload: JobMatchRequest) -> dict:
    # Import optional ML libraries in the worker thread as well as running inference there.
    from app.services.job_matcher import JobMatcherService

    return JobMatcherService().analyze_compatibility(payload.cv_data, payload.job_description)


@router.post("/match-job", response_model=JobMatchResponse)
async def match_job_endpoint(payload: JobMatchRequest, request: Request) -> JobMatchResponse:
    if settings.API_KEY and not hmac.compare_digest(
        request.headers.get("x-api-key", ""), settings.API_KEY.get_secret_value()
    ):
        raise HTTPException(401, "Invalid API key.")
    slots = request.app.state.parse_slots
    if slots.locked():
        raise HTTPException(503, "Analysis capacity reached; retry later.", headers={"Retry-After": "5"})
    async with slots:
        start = time.perf_counter()
        try:
            result = await run_in_threadpool(analyze_job, payload)
        except Exception as exc:
            logger.bind(error_type=type(exc).__name__).error("job_match_failed")
            raise HTTPException(500, "Job compatibility analysis failed.") from exc
        logger.bind(
            semantic_method=result["semantic_method"], elapsed_ms=round((time.perf_counter() - start) * 1000)
        ).info("job_match_complete")
        return JobMatchResponse.model_validate(result)


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
                if settings.IS_VERCEL:
                    data = source.read_bytes()
                    try:
                        resume = ResumeParserService().parse_pdf(data, file.filename)
                        result = adapt_resume(resume) if dashboard else resume
                    except CVParserException as exc:
                        raise HTTPException(exc.status_code, {"code": exc.code, "message": str(exc)}) from exc
                    except Exception as exc:
                        logger.bind(request_id=request_id, error_type=type(exc).__name__).error(
                            "parse_failed"
                        )
                        raise HTTPException(500, "Document processing failed. Please retry.") from exc
                    logger.bind(request_id=request_id, serverless=True).info("parse_complete")
                    return result
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
