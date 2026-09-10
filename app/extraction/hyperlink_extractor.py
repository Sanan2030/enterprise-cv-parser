import re
from dataclasses import dataclass
from urllib.parse import unquote

import pymupdf as fitz


@dataclass(frozen=True)
class Hyperlink:
    url: str
    page: int
    bbox: tuple[float, float, float, float]


class HyperlinkExtractor:
    _URI_PATTERN = re.compile(r"/URI\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]+>)")

    @staticmethod
    def _decode_pdf_uri(value: str) -> str | None:
        """Decode PDF literal/hex strings from a URI action without evaluating PDF data."""
        if value.startswith("<"):
            try:
                raw = bytes.fromhex(re.sub(r"\s", "", value[1:-1]))
                return (
                    raw.decode("utf-16")
                    if raw.startswith((b"\xfe\xff", b"\xff\xfe"))
                    else raw.decode("utf-8")
                )
            except (UnicodeDecodeError, ValueError):
                return None
        content = value[1:-1]
        output: list[str] = []
        index = 0
        while index < len(content):
            if content[index] != "\\" or index + 1 == len(content):
                output.append(content[index])
                index += 1
                continue
            index += 1
            if content[index] in "nrtbf":
                output.append({"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}[content[index]])
                index += 1
            elif content[index].isdigit():
                end = index
                while end < min(index + 3, len(content)) and content[end].isdigit():
                    end += 1
                output.append(chr(int(content[index:end], 8)))
                index = end
            else:
                output.append(content[index])
                index += 1
        return unquote("".join(output))

    @staticmethod
    def extract(page: fitz.Page) -> list[Hyperlink]:
        links = [
            Hyperlink(link["uri"], page.number + 1, tuple(link["from"]))
            for link in page.get_links()
            if link.get("uri")
        ]
        known = {link.url for link in links}
        for xref, kind, _ in page.annot_xrefs():
            if kind != fitz.PDF_ANNOT_LINK:
                continue
            action = page.parent.xref_get_key(xref, "A")
            if action[0] != "dict":
                continue
            match = HyperlinkExtractor._URI_PATTERN.search(action[1])
            url = HyperlinkExtractor._decode_pdf_uri(match[1]) if match else None
            if not url or url in known:
                continue
            rect = page.parent.xref_get_key(xref, "Rect")
            coordinates = [float(number) for number in re.findall(r"-?\d+(?:\.\d+)?", rect[1])]
            if len(coordinates) != 4:
                continue
            annotation = fitz.Rect(coordinates)
            links.append(Hyperlink(url, page.number + 1, tuple(annotation * page.transformation_matrix)))
            known.add(url)
        return links
