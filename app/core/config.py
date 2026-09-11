import os
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    PROJECT_NAME: str = "Enterprise CV Parser"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    MAX_UPLOAD_SIZE_MB: int = Field(15, ge=1, le=15)
    MAX_PAGES: int = Field(30, ge=1, le=100)
    MAX_TEXT_CHARS: int = Field(300_000, ge=1000)
    MAX_PAGE_PIXELS: int = Field(20_000_000, ge=1_000_000)
    OCR_DPI: int = Field(220, ge=100, le=300)
    OCR_TIMEOUT: int = Field(30, ge=1, le=120)
    OCR_LANGUAGES: str = "eng+aze+tur+rus"
    TESSERACT_CMD: str = "tesseract"
    PARSE_TIMEOUT: int = Field(120, ge=1, le=600)
    MAX_CONCURRENT_PARSES: int = Field(2, ge=1, le=8)
    DEFAULT_PHONE_REGION: str = "AZ"
    SPACY_MODEL: str | None = None
    API_KEY: SecretStr | None = None
    USE_LLM_FALLBACK: bool = False
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    LLM_THRESHOLD: float = Field(0.65, ge=0, le=1)
    LLM_MAX_CHARS: int = Field(30_000, ge=1000)
    IS_VERCEL: bool = os.getenv("VERCEL") == "1"
    MATCH_SEMANTIC_BACKEND: Literal["auto", "tfidf"] = "auto"
    MATCH_MODEL_LOCAL_ONLY: bool = True
    MATCH_RERANK_ENABLED: bool = True
    MATCH_RERANK_TIMEOUT: int = Field(8, ge=1, le=30)
    MATCH_RERANK_MEMORY_MB: int = Field(4096, ge=512, le=16384)


settings = Settings()
