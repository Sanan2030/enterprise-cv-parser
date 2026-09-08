class CVParserException(Exception):
    """Safe client-facing error; never include document text."""

    status_code = 422
    code = "parse_error"


class InvalidPDFException(CVParserException):
    code = "invalid_pdf"


class SecurityException(CVParserException):
    status_code = 413
    code = "document_limit"


class OCRError(CVParserException):
    status_code = 503
    code = "ocr_unavailable"
