import json
import sys
from pathlib import Path

from app.core.exceptions import CVParserException
from app.core.logging import configure_logging, logger
from app.services.resume_parser import ResumeParserService


def main() -> int:
    configure_logging()
    source, destination, filename = sys.argv[1:4]
    try:
        data = Path(source).read_bytes()
        result = ResumeParserService().parse_pdf(data, filename)
        if len(sys.argv) > 4 and sys.argv[4] == "dashboard":
            from app.services.dashboard_adapter import adapt_resume

            dashboard = adapt_resume(result)
            payload = {"result": dashboard.model_dump(mode="json")}
        else:
            payload = {"result": result.model_dump(mode="json")}
    except CVParserException as exc:
        payload = {"error": {"status": exc.status_code, "code": exc.code, "message": str(exc)}}
    except Exception as exc:
        logger.bind(error_type=type(exc).__name__).error("worker_failed")
        payload = {
            "error": {"status": 500, "code": "internal_error", "message": "Document processing failed."}
        }
    Path(destination).write_text(json.dumps(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
