from app.extraction.layout_engine import LayoutBlock
from app.schemas.resume import FieldWithMetadata, Provenance


def provenance(block: LayoutBlock, confidence: float = 0.8) -> Provenance:
    return Provenance(
        page=block.page_num, source_text=block.text, confidence=min(confidence, block.confidence)
    )


def sourced(
    value: str | None, blocks: list[LayoutBlock], confidence: float = 0.8
) -> FieldWithMetadata | None:
    if not value:
        return None
    block = next((b for b in blocks if value.casefold() in b.text.casefold()), None)
    if block is None:
        return None
    source = provenance(block, confidence)
    return FieldWithMetadata(value=value, confidence=source.confidence, provenance=source)
