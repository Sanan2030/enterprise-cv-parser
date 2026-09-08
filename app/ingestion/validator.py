import re
from pathlib import PurePath

import pymupdf as fitz

from app.core.config import settings
from app.core.exceptions import InvalidPDFException, SecurityException


class PDFValidator:
    @staticmethod
    def validate_file(file_bytes: bytes, filename: str) -> int:
        if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise SecurityException("PDF exceeds the upload limit.")
        if PurePath(filename).suffix.lower() != ".pdf":
            raise InvalidPDFException("Only PDF files are accepted.")
        if not re.match(rb"%PDF-\d\.\d", file_bytes[:8]):
            raise InvalidPDFException("Invalid PDF header.")
        if b"%%EOF" not in file_bytes[-2048:]:
            raise InvalidPDFException("Missing PDF end marker.")
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                if doc.needs_pass or doc.is_encrypted or doc.metadata.get("encryption"):
                    raise InvalidPDFException("Encrypted PDFs are not supported.")
                if doc.is_repaired:
                    raise InvalidPDFException("Damaged PDF requires repair before upload.")
                if not doc.page_count:
                    raise InvalidPDFException("PDF contains no pages.")
                if doc.page_count > settings.MAX_PAGES:
                    raise SecurityException("PDF exceeds the page limit.")
                for page in doc:
                    if page.rect.is_empty or page.rect.is_infinite:
                        raise InvalidPDFException("Invalid page geometry.")
                return doc.page_count
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise InvalidPDFException("Cannot read PDF structure.") from exc
