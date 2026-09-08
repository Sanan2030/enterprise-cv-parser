from collections import defaultdict

import pymupdf as fitz
import pytesseract
from PIL import Image

from app.core.config import settings
from app.core.exceptions import OCRError, SecurityException
from app.extraction.layout_engine import LayoutBlock


class OCREngine:
    def extract_page(self, page: fitz.Page) -> tuple[list[LayoutBlock], list[str]]:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        try:
            available = set(pytesseract.get_languages(config=""))
            requested = settings.OCR_LANGUAGES.split("+")
            languages = [lang for lang in requested if lang in available]
            if not languages:
                raise OCRError("No configured OCR language packs are installed.")
            warnings = ["OCR language unavailable: " + lang for lang in requested if lang not in available]
            scale = settings.OCR_DPI / 72
            if page.rect.width * page.rect.height * scale**2 > settings.MAX_PAGE_PIXELS:
                raise SecurityException("Page exceeds the OCR pixel limit.")
            pix = page.get_pixmap(dpi=settings.OCR_DPI, colorspace=fitz.csRGB, alpha=False)
            with Image.frombytes("RGB", (pix.width, pix.height), pix.samples) as image:
                data = pytesseract.image_to_data(
                    image,
                    lang="+".join(languages),
                    config="--psm 3",
                    output_type=pytesseract.Output.DICT,
                    timeout=settings.OCR_TIMEOUT,
                )
            lines = defaultdict(list)
            for i, word in enumerate(data["text"]):
                if word.strip() and float(data["conf"][i]) >= 0:
                    lines[(data["block_num"][i], data["par_num"][i], data["line_num"][i])].append(i)
            blocks = []
            for indices in lines.values():
                x0 = min(data["left"][i] for i in indices) / scale
                y0 = min(data["top"][i] for i in indices) / scale
                x1 = max(data["left"][i] + data["width"][i] for i in indices) / scale
                y1 = max(data["top"][i] + data["height"][i] for i in indices) / scale
                blocks.append(
                    LayoutBlock(
                        (x0, y0, x1, y1),
                        " ".join(data["text"][i] for i in indices),
                        page.number + 1,
                        method="ocr",
                        confidence=sum(float(data["conf"][i]) for i in indices) / len(indices) / 100,
                    )
                )
            return blocks, warnings
        except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, RuntimeError, OSError) as exc:
            raise OCRError("OCR failed or exceeded its time limit.") from exc
