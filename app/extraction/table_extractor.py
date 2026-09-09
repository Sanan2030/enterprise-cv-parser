from io import BytesIO

import pdfplumber

from app.core.exceptions import SecurityException
from app.schemas.dashboard import Table


class TableExtractor:
    """Extract native ruled tables; no invented OCR table reconstruction."""

    @staticmethod
    def extract(data: bytes) -> list[Table]:
        tables = []
        cells = 0
        with pdfplumber.open(BytesIO(data)) as doc:
            for number, page in enumerate(doc.pages, 1):
                for raw in page.extract_tables():
                    if not raw or len(raw) < 2:
                        continue
                    width = max(len(row) for row in raw)
                    if width < 2:
                        continue
                    cells += len(raw) * width
                    if cells > 5000:
                        raise SecurityException("Table extraction exceeds the cell limit.")
                    rows = [
                        [str(cell or "").strip() for cell in row] + [""] * (width - len(row)) for row in raw
                    ]
                    # Preserve the first row as data: a visible grid does not prove it is a header.
                    tables.append(
                        Table(
                            title=f"Page {number} · Table {len(tables) + 1}",
                            headers=[f"Column {i + 1}" for i in range(width)],
                            rows=rows,
                        )
                    )
        return tables
