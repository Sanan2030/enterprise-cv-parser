"""Detect invisible text and suspect font mappings before entity parsing."""

import re

import pymupdf as fitz


def hidden_text(page: fitz.Page) -> set[tuple[tuple[float, ...], str]]:
    """Ignore fully overpainted spans, not text simply drawn over a background."""
    fills = [
        d
        for d in page.get_drawings()
        if d.get("fill") is not None
        and d.get("fill_opacity", 0) == 1
        and len(d["items"]) == 1
        and d["items"][0][0] == "re"
    ]
    hidden = set()
    for span in page.get_texttrace():
        if (
            span["type"] == 3
            or span.get("opacity", 1) == 0
            or any(d["seqno"] > span["seqno"] and d["rect"].contains(fitz.Rect(span["bbox"])) for d in fills)
        ):
            hidden.add((tuple(round(v, 1) for v in span["bbox"]), "".join(chr(c[0]) for c in span["chars"])))
    return hidden


def is_hidden(text: str, bbox: tuple, hidden: set) -> bool:
    # Text trace and dictionary extraction use different ascender boxes.
    return any(
        text == value
        and abs(bbox[0] - rect[0]) < 1
        and abs(bbox[2] - rect[2]) < 1
        and abs(bbox[3] - rect[3]) < 6
        for rect, value in hidden
    )


def conflicting_cmap(page: fitz.Page) -> bool:
    """Colliding alphabetic mappings can silently corrupt otherwise readable text."""
    for font in page.get_fonts():
        kind, value = page.parent.xref_get_key(font[0], "ToUnicode")
        if kind != "xref":
            continue
        data = page.parent.xref_stream(int(value.split()[0])) or b""
        for section in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
            seen = {}
            for source, target in re.findall(rb"<([\da-fA-F]+)>\s*<([\da-fA-F]+)>", section):
                if len(target) != 4:
                    continue
                codepoint = int(target, 16)
                if not chr(codepoint).isalpha():
                    continue
                if codepoint in seen and seen[codepoint] != source:
                    return True
                seen[codepoint] = source
    return False


def has_unknown_characters(text: str) -> bool:
    return any(ord(c) < 32 and c not in "\n\t\r" or c == "\ufffd" for c in text)
