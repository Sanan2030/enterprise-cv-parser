"""MuPDF's built-in Tesseract OCR; no external executable is required."""

import hashlib
import os
import re
import tempfile
import time
from pathlib import Path
from threading import Lock

import httpx
import pymupdf as fitz

from app.core.config import settings
from app.core.exceptions import OCRError, SecurityException
from app.extraction.layout_engine import LayoutBlock
from app.parsing.section_classifier import SectionClassifier

MODEL_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata"
MODEL_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
MODEL_SIZE = 4113088
_model_lock = Lock()


def english_model_directory() -> Path:
    """Cache a checksum-verified public model, never document data."""
    directory = Path(tempfile.gettempdir()) / "cv-parser-tessdata-4.1.0"
    with _model_lock:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = directory / "eng.traineddata"
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == MODEL_SHA256:
            return directory
        started = time.monotonic()
        data = bytearray()
        try:
            with httpx.stream("GET", MODEL_URL, timeout=20) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MODEL_SIZE or time.monotonic() - started > 30:
                        raise OCRError("OCR model download exceeded its limit. Please retry.")
            if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
                raise OCRError("OCR model integrity check failed. Please retry.")
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                try:
                    stream.write(data)
                    stream.flush()
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
        except (httpx.HTTPError, OSError) as exc:
            raise OCRError("OCR model could not be loaded. Please retry or upload a text-based PDF.") from exc
        return directory


class ServerlessOCREngine:
    def extract_page(self, page: fitz.Page) -> tuple[list[LayoutBlock], list[str]]:
        scale = settings.OCR_DPI / 72
        if page.rect.width * page.rect.height * scale**2 > settings.MAX_PAGE_PIXELS:
            raise SecurityException("Page exceeds the OCR pixel limit.")
        directory = english_model_directory()
        try:
            textpage = page.get_textpage_ocr(
                language="eng", dpi=settings.OCR_DPI, full=True, tessdata=str(directory)
            )
            blocks = []
            for group in textpage.extractDICT()["blocks"]:
                for line in group.get("lines", []):
                    spans = line["spans"]
                    text = " ".join(" ".join(s["text"] for s in spans).split())
                    if text:
                        blocks.append(
                            LayoutBlock(
                                tuple(line["bbox"]),
                                text,
                                page.number + 1,
                                max(s["size"] for s in spans),
                                method="ocr",
                                confidence=0.65,
                            )
                        )
            # Decorative backgrounds may suppress the top title in full-page OCR.
            # Retry only the missing top band, keeping the extracted source geometry.
            if blocks and min(b.y0 for b in blocks) > page.rect.height * 0.09:
                clip = fitz.Rect(0, 0, page.rect.width, page.rect.height * 0.18)
                pixmap = page.get_pixmap(dpi=settings.OCR_DPI, clip=clip, colorspace=fitz.csRGB, alpha=False)
                with fitz.open(
                    stream=pixmap.pdfocr_tobytes(language="eng", tessdata=str(directory)), filetype="pdf"
                ) as header:
                    for group in header[0].get_text("dict")["blocks"]:
                        for line in group.get("lines", []):
                            if line["bbox"][1] >= min(b.y0 for b in blocks):
                                continue
                            spans = line["spans"]
                            text = " ".join(" ".join(s["text"] for s in spans).split())
                            if text:
                                blocks.append(
                                    LayoutBlock(
                                        tuple(line["bbox"]),
                                        text,
                                        page.number + 1,
                                        max(s["size"] for s in spans),
                                        method="ocr",
                                        confidence=0.65,
                                    )
                                )
            # Retry separated columns so tinted sidebars and nearby paragraph text
            # do not interfere with each other's OCR segmentation.
            positions = sorted(
                {
                    b.x0
                    for b in blocks
                    if b.y0 > page.rect.height * 0.18 and len(b.text) > 5 and b.x0 < page.rect.width * 0.7
                }
            )
            gaps = [(right - left, right) for left, right in zip(positions, positions[1:])]
            if gaps:
                gap, right = max(gaps)
                cut = right - 12
                if gap > page.rect.width * 0.18 and page.rect.width * 0.25 < cut < page.rect.width * 0.65:
                    for x0, x1 in [(0, cut), (cut, page.rect.width)]:
                        top = page.rect.height * 0.18
                        bottom = page.rect.height
                        if x0 == 0:
                            headings = [
                                b.y0
                                for b in blocks
                                if b.x0 < cut and SectionClassifier.classify_block(b.text)[0] == "education"
                            ]
                            if headings:
                                top = min(headings) - 5
                                following = [
                                    b.y0
                                    for b in blocks
                                    if b.x0 < cut
                                    and b.y0 > top + 10
                                    and SectionClassifier.classify_block(b.text)[0] == "skills"
                                ]
                                if following:
                                    bottom = min(following) - 3
                        clip = fitz.Rect(x0, top, x1, bottom)
                        pixmap = page.get_pixmap(
                            dpi=settings.OCR_DPI, clip=clip, colorspace=fitz.csRGB, alpha=False
                        )
                        replacement = []
                        with fitz.open(
                            stream=pixmap.pdfocr_tobytes(language="eng", tessdata=str(directory)),
                            filetype="pdf",
                        ) as column:
                            for group in column[0].get_text("dict")["blocks"]:
                                for line in group.get("lines", []):
                                    spans = line["spans"]
                                    text = " ".join(" ".join(s["text"] for s in spans).split())
                                    if not re.search(r"\w{2}", text):
                                        continue
                                    text = re.sub(r"(?<!\S)\|(?=\s+[A-Za-z])", "I", text)
                                    a, b, c, d = line["bbox"]
                                    replacement.append(
                                        LayoutBlock(
                                            (a + x0, b + top, c + x0, d + top),
                                            text,
                                            page.number + 1,
                                            max(s["size"] for s in spans),
                                            method="ocr",
                                            confidence=0.65,
                                        )
                                    )
                        if replacement:
                            blocks = [
                                b for b in blocks if not (x0 <= b.x0 < x1 and top <= b.y0 < bottom)
                            ] + replacement
            blocks = [b for b in blocks if re.search(r"\w{2}", b.text)]
        except (RuntimeError, ValueError) as exc:
            raise OCRError("Image-based PDF OCR failed. Try a clearer scan or a text-based PDF.") from exc
        return blocks, [
            "English OCR was used for scanned content. Review names, dates and links against the PDF."
        ]
