import re
import time
from pathlib import PurePath

from app.core.config import settings
from app.extraction.text_extractor import PDFTextExtractor
from app.intelligence.confidence import ConfidenceScorer
from app.intelligence.llm_fallback import LLMFallbackService
from app.intelligence.provenance import provenance
from app.parsing.education_parser import EducationParser
from app.parsing.entity_extractor import EntityExtractor
from app.parsing.experience_parser import ExperienceParser
from app.parsing.language_detector import DocumentLanguageDetector
from app.parsing.section_classifier import SectionClassifier
from app.parsing.skill_extractor import SkillExtractor
from app.schemas.resume import (
    Certification,
    DocumentMetadata,
    FieldWithMetadata,
    LanguageSkill,
    ProfessionalProfile,
    Project,
    QualityControl,
    ResumeParsedSchema,
)


class ResumeParserService:
    def parse_pdf(self, pdf_bytes: bytes, filename: str) -> ResumeParsedSchema:
        start = time.perf_counter()
        extraction = PDFTextExtractor().extract(pdf_bytes, filename)
        blocks = extraction.blocks
        sections = SectionClassifier().segment_document(blocks)
        header = sections["header"] + sections["personal_information"]
        personal = EntityExtractor().extract(header, blocks, extraction.links)
        profile = ProfessionalProfile()
        summaries = sections["professional_summary"]
        if summaries:
            profile.professional_summary = FieldWithMetadata(
                value="\n".join(b.text for b in summaries),
                confidence=0.8,
                provenance=provenance(summaries[0], 0.8),
            )
        text = "\n".join(b.text for b in blocks)
        warnings = list(extraction.warnings)
        if not settings.SPACY_MODEL:
            warnings.append("spaCy NER model not configured; name extraction uses conservative heuristics.")
        result = ResumeParsedSchema(
            document=DocumentMetadata(
                file_name=PurePath(filename.replace("\\", "/")).name,
                page_count=extraction.page_count,
                document_language=DocumentLanguageDetector().detect(text),
                processing_time_ms=0,
            ),
            personal_information=personal,
            professional_profile=profile,
            work_experience=ExperienceParser().parse(sections["work_experience"]),
            education=EducationParser().parse(sections["education"]),
            skills=SkillExtractor().extract_skills(text, "\n".join(b.text for b in sections["skills"])),
            certifications=[Certification(certification_name=b.text) for b in sections["certifications"]],
            projects=[Project(project_name=b.text) for b in sections["projects"]],
            raw_sections={key: [provenance(b) for b in value] for key, value in sections.items() if value},
            quality=QualityControl(warnings=warnings, extraction_method=extraction.method),
        )
        for block in sections["languages"]:
            for item in re.split(r"[,;]", block.text):
                parts = re.split(r"\s*[:–—-]\s*", item.strip(), maxsplit=1)
                if not parts[0]:
                    continue
                level = re.search(r"\b[ABC][12]\b", item, re.I)
                result.languages.append(
                    LanguageSkill(
                        language=parts[0],
                        proficiency=parts[1] if len(parts) > 1 else None,
                        cefr_level=level[0].upper() if level else None,
                    )
                )
        result.quality = ConfidenceScorer.calculate_quality(result)
        if settings.USE_LLM_FALLBACK and (
            result.quality.overall_confidence < settings.LLM_THRESHOLD or result.quality.missing_sections
        ):
            changed = LLMFallbackService().enrich(result, blocks)
            result.quality.warnings.append(
                "LLM supplied evidence-checked fields."
                if changed
                else "LLM fallback did not add validated fields."
            )
            result.quality = ConfidenceScorer.calculate_quality(result)
        result.document.processing_time_ms = round((time.perf_counter() - start) * 1000, 2)
        # Revalidate all nested values before crossing the service boundary.
        return ResumeParsedSchema.model_validate(result.model_dump())
