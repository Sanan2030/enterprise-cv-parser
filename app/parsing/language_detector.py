from collections import Counter
from functools import lru_cache

from lingua import Language, LanguageDetector, LanguageDetectorBuilder

from app.schemas.resume import LanguageDetectionResult


@lru_cache(maxsize=1)
def detector() -> LanguageDetector:
    return (
        LanguageDetectorBuilder.from_languages(
            Language.ENGLISH,
            Language.AZERBAIJANI,
            Language.TURKISH,
            Language.RUSSIAN,
            Language.GERMAN,
            Language.FRENCH,
            Language.SPANISH,
        )
        .with_low_accuracy_mode()
        .build()
    )


class DocumentLanguageDetector:
    def detect(self, text: str) -> LanguageDetectionResult:
        if sum(c.isalpha() for c in text) < 15:
            return LanguageDetectionResult()
        values = detector().compute_language_confidence_values(text[:12000])
        if not values or values[0].value < 0.4:
            return LanguageDetectionResult()
        primary = values[0].language.iso_code_639_1.name.lower()
        counts = Counter()
        for line in text.splitlines()[:200]:
            if sum(c.isalpha() for c in line) < 25:
                continue
            scores = detector().compute_language_confidence_values(line)
            if scores and scores[0].value >= 0.75:
                counts[scores[0].language.iso_code_639_1.name.lower()] += 1
        return LanguageDetectionResult(
            primary=primary,
            secondary=[lang for lang, count in counts.items() if lang != primary and count >= 2],
            confidence=round(values[0].value, 3),
        )
