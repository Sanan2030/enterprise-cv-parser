from app.schemas.resume import QualityControl, ResumeParsedSchema


class ConfidenceScorer:
    @staticmethod
    def calculate_quality(resume: ResumeParsedSchema) -> QualityControl:
        fields = {
            "personal_information.full_name": resume.personal_information.full_name,
            "personal_information.email": resume.personal_information.email,
            "professional_profile.professional_summary": resume.professional_profile.professional_summary,
        }
        scores = [field.confidence for field in fields.values() if field and field.value]
        scores += [
            item.provenance.confidence
            for item in [*resume.work_experience, *resume.education]
            if item.provenance
        ]
        missing = [key for key, value in fields.items() if not value]
        missing += [key for key in ["work_experience", "education"] if not getattr(resume, key)]
        warnings = list(resume.quality.warnings)
        if missing:
            warnings.append("Some expected fields are absent; consult raw_sections.")
        warnings.append("Confidence is a heuristic evidence score, not a calibrated accuracy probability.")
        return QualityControl(
            overall_confidence=round(sum(scores) / len(scores), 3) if scores else 0,
            warnings=list(dict.fromkeys(warnings)),
            missing_sections=missing,
            extraction_method=resume.quality.extraction_method,
        )
