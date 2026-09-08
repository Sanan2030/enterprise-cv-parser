from dataclasses import dataclass

import pymupdf as fitz


@dataclass(frozen=True)
class Hyperlink:
    url: str
    page: int
    bbox: tuple[float, float, float, float]


class HyperlinkExtractor:
    @staticmethod
    def extract(page: fitz.Page) -> list[Hyperlink]:
        return [
            Hyperlink(link["uri"], page.number + 1, tuple(link["from"]))
            for link in page.get_links()
            if link.get("uri")
        ]
