import re
import unicodedata
from dataclasses import replace

from rapidfuzz import fuzz

from app.extraction.layout_engine import LayoutBlock

SECTION_DICTIONARY = {
    "personal_information": [
        "contact",
        "personal info",
        "personal details",
        "əlaqə",
        "kişisel bilgiler",
        "kontakte",
    ],
    "professional_summary": [
        "summary",
        "profile",
        "about me",
        "professional summary",
        "career profile",
        "haqqımda",
        "xülasə",
        "özet",
        "о себе",
        "профиль",
        "zusammenfassung",
    ],
    "work_experience": [
        "work experience",
        "experience",
        "employment history",
        "career history",
        "work history",
        "iş təcrübəsi",
        "təcrübə",
        "iş deneyimi",
        "опыт работы",
        "berufserfahrung",
        "expérience",
    ],
    "education": [
        "education",
        "academic background",
        "qualifications",
        "təhsil",
        "eğitim",
        "образование",
        "ausbildung",
    ],
    "skills": [
        "skills",
        "technical skills",
        "core competencies",
        "expertise",
        "bacarıqlar",
        "yetenekler",
        "навыки",
        "fähigkeiten",
        "competences",
    ],
    "certifications": [
        "certifications",
        "certificates",
        "sertifikatlar",
        "sertifikalar",
        "сертификаты",
        "zertifikate",
    ],
    "languages": ["languages", "language proficiency", "dil bilikləri", "diller", "языки", "sprachen"],
    "projects": ["projects", "personal projects", "layihələr", "projeler", "проекты", "projekte"],
}


class SectionClassifier:
    @staticmethod
    def classify_block(text: str) -> tuple[str | None, float]:
        clean = unicodedata.normalize("NFKC", text).casefold().strip().rstrip(":：").strip()
        if not clean or len(clean) > 48 or len(clean.split()) > 5 or re.search(r"[.!?;,]", clean):
            return None, 0.0
        scores = []
        for section, keywords in SECTION_DICTIONARY.items():
            for keyword in keywords:
                if clean == keyword:
                    return section, 1.0
                if len(clean.split()) != len(keyword.split()) or min(len(clean), len(keyword)) < 5:
                    continue
                scores.append((fuzz.ratio(clean, keyword), section))
        if not scores:
            return None, 0.0
        score, section = max(scores)
        return (section, round(score / 100, 2)) if score >= 90 else (None, 0.0)

    def segment_document(self, blocks: list[LayoutBlock]) -> dict[str, list[LayoutBlock]]:
        segmented = {key: [] for key in ["header", *SECTION_DICTIONARY]}
        current = "header"
        for block in blocks:
            for text in block.text.splitlines():
                candidate = replace(block, text=text.strip())
                if not candidate.text:
                    continue
                label, separator, content = candidate.text.partition(":")
                section, score = self.classify_block(label if separator else candidate.text)
                if section and (score == 1 or block.is_bold or block.font_size >= 12):
                    current = section
                    if separator and content.strip():
                        segmented[current].append(replace(candidate, text=content.strip()))
                else:
                    segmented[current].append(candidate)
        return segmented
