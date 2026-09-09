FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-aze tesseract-ocr-tur tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install -c constraints.txt '.[ocr,nlp]' && useradd --create-home --uid 10001 parser

FROM base AS test
RUN pip install -c constraints.txt '.[test,ocr,nlp]'
USER parser
CMD ["pytest", "-q", "-p", "no:cacheprovider"]

FROM base AS production
USER parser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "16", "--no-access-log"]
