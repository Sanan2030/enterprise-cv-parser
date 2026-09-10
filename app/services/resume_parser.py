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
from app.parsing.language_skills import parse_languages
from app.parsing.section_classifier import SectionClassifier
from app.parsing.skill_extractor import SkillExtractor
from app.parsing.structured_sections import parse_certifications, parse_projects
from app.schemas.resume import (
    DocumentMetadata,
    FieldWithMetadata,
    ProfessionalProfile,
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
        candidate_blocks = [
            b for key, group in sections.items() if key not in {"references", "interests"} for b in group
        ]
        personal = EntityExtractor().extract(header, candidate_blocks, extraction.links)
        profile = ProfessionalProfile()
        summaries = sections["professional_summary"]
        if summaries:
            profile.professional_summary = FieldWithMetadata(
                value="\n".join(b.text for b in summaries),
                confidence=0.8,
                provenance=provenance(summaries[0], 0.8),
            )
        text = "\n".join(b.text for b in candidate_blocks)
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
            skills=SkillExtractor().extract_skills(text, SkillExtractor.section_text(sections["skills"])),
            certifications=parse_certifications(sections["certifications"]),
            projects=parse_projects(sections["projects"]),
            raw_sections={key: [provenance(b) for b in value] for key, value in sections.items() if value},
            quality=QualityControl(warnings=warnings, extraction_method=extraction.method),
        )
        result.languages = parse_languages(sections["languages"])
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
