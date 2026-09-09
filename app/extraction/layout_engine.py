from dataclasses import dataclass, replace


@dataclass(frozen=True)
class LayoutBlock:
    bbox: tuple[float, float, float, float]
    text: str
    page_num: int
    font_size: float = 0.0
    is_bold: bool = False
    method: str = "native"
    confidence: float = 0.95

    @property
    def x0(self) -> float:
        return self.bbox[0]

    @property
    def y0(self) -> float:
        return self.bbox[1]

    @property
    def x1(self) -> float:
        return self.bbox[2]

    @property
    def y1(self) -> float:
        return self.bbox[3]


class DocumentLayoutEngine:
    """Find a low-crossing vertical gutter, retaining spanning title/footer bands."""

    @staticmethod
    def sort_reading_order(blocks: list[LayoutBlock], page_width: float) -> list[LayoutBlock]:
        if len({b.page_num for b in blocks}) > 1:
            return [
                b
                for page in sorted({b.page_num for b in blocks})
                for b in DocumentLayoutEngine.sort_reading_order(
                    [b for b in blocks if b.page_num == page], page_width
                )
            ]
        ordered = sorted(blocks, key=lambda b: (b.y0, b.x0))
        from app.parsing.section_classifier import SectionClassifier

        # A heading is a band boundary only when there is no other-column text
        # beside it. Independent sidebar headings must not split the main column.
        headings = [
            b
            for b in ordered
            if SectionClassifier.classify_block(b.text)[0]
            and not any(o is not b and o.y0 < b.y1 and o.y1 > b.y0 for o in ordered)
        ]
        if headings:
            result = []
            remaining = list(ordered)
            for heading in headings:
                before = [b for b in remaining if b.y0 < heading.y0]
                result.extend(DocumentLayoutEngine.sort_reading_order(before, page_width))
                result.append(heading)
                remaining = [b for b in remaining if b.y0 >= heading.y0 and b is not heading]
            return result + DocumentLayoutEngine.sort_reading_order(remaining, page_width)
        if len(blocks) < 4:
            return ordered
        candidates = []
        for percent in range(20, 81):
            cut = page_width * percent / 100
            left = [b for b in blocks if b.x1 <= cut]
            right = [b for b in blocks if b.x0 >= cut]
            span = [b for b in blocks if b.x0 < cut < b.x1]
            if len(left) < 2 or len(right) < 2 or len(span) > len(blocks) * 0.4:
                continue
            if max(min(b.y0 for b in left), min(b.y0 for b in right)) >= min(
                max(b.y1 for b in left), max(b.y1 for b in right)
            ):
                continue
            gap = min(b.x0 for b in right) - max(b.x1 for b in left)
            if gap >= max(12, page_width * 0.025):
                candidates.append((gap - len(span) * 10, cut, span))
        if not candidates:
            return ordered
        _, cut, spanning = max(candidates, key=lambda item: item[0])
        remaining = [b for b in ordered if b not in spanning]
        result = []

        def columns(items: list[LayoutBlock]) -> list[LayoutBlock]:
            return sorted(items, key=lambda b: (b.x0 >= cut, b.y0, b.x0))

        for band in sorted(spanning, key=lambda b: (b.y0, b.x0)):
            preceding = [b for b in remaining if (b.y0 + b.y1) / 2 < (band.y0 + band.y1) / 2]
            result.extend(columns(preceding))
            remaining = [b for b in remaining if b not in preceding]
            result.append(band)
        return result + columns(remaining)

    @staticmethod
    def join_line_fragments(blocks: list[LayoutBlock]) -> list[LayoutBlock]:
        """Join near-baseline fragments, but never cross a new bullet/column."""
        from app.normalization.date_normalizer import RANGE_PATTERN

        rows: list[list[LayoutBlock]] = []
        for block in sorted(blocks, key=lambda b: (b.y0, b.x0)):
            row = next((r for r in reversed(rows[-3:]) if abs(r[0].y0 - block.y0) < 1.5), None)
            if row is None:
                rows.append([block])
            else:
                row.append(block)
        output = []
        for row in rows:
            merged: list[LayoutBlock] = []
            for block in sorted(row, key=lambda b: b.x0):
                date_suffix = bool(RANGE_PATTERN.fullmatch(block.text.strip()))
                if merged and (
                    date_suffix
                    or (
                        block.x0 - merged[-1].x1 <= max(3, block.font_size * 0.9)
                        and not block.text.startswith(("•", "●", "▪"))
                    )
                ):
                    previous = merged[-1]
                    merged[-1] = replace(
                        previous,
                        text=previous.text + " " + block.text,
                        bbox=(previous.x0, min(previous.y0, block.y0), block.x1, max(previous.y1, block.y1)),
                    )
                else:
                    merged.append(block)
            output.extend(merged)
        return output
