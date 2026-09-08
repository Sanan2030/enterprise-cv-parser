from unittest.mock import patch

import httpx
from pydantic import SecretStr

from app.core.config import settings
from app.intelligence.llm_fallback import LLMFallbackService, Suggestion, Suggestions
from app.services.resume_parser import ResumeParserService


def test_disabled_no_request():
    with patch("httpx.Client") as client:
        assert LLMFallbackService().parse_with_llm("text") is None
        client.assert_not_called()


def test_schema_validation_and_http_failure(monkeypatch):
    monkeypatch.setattr(settings, "USE_LLM_FALLBACK", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("test-secret"))
    with patch("httpx.Client") as cls:
        response = cls.return_value.__enter__.return_value.post.return_value
        response.json.return_value = {
            "choices": [{"message": {"content": '{"suggestions": [{"field": "email"}]}'}}]
        }
        assert LLMFallbackService().parse_with_llm("text") is None
        response.raise_for_status.side_effect = httpx.ConnectError("offline")
        assert LLMFallbackService().parse_with_llm("text") is None


def test_validated_recovery_and_reject_hallucination(pdf_bytes, block):
    result = ResumeParserService().parse_pdf(pdf_bytes, "resume.pdf")
    result.personal_information.full_name = None
    suggestions = Suggestions(
        suggestions=[Suggestion(field="full_name", value="Invented Name", quote="Invented Name", page=1)]
    )
    with patch.object(LLMFallbackService, "parse_with_llm", return_value=suggestions):
        assert not LLMFallbackService().enrich(result, [block("Alex Morgan")])
    suggestions.suggestions[0] = Suggestion(
        field="full_name", value="Alex Morgan", quote="Alex Morgan", page=1
    )
    with patch.object(LLMFallbackService, "parse_with_llm", return_value=suggestions):
        assert LLMFallbackService().enrich(result, [block("Alex Morgan")])
    assert result.personal_information.full_name.value == "Alex Morgan"
