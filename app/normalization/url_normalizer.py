import re
from urllib.parse import urlsplit, urlunsplit


class URLNormalizer:
    @staticmethod
    def normalize(value: str) -> str | None:
        value = value.strip().rstrip(".,;)")
        if re.search(r"[\s\x00-\x1f]", value):
            return None
        if "://" not in value:
            value = "https://" + value
        try:
            p = urlsplit(value)
            host = (p.hostname or "").encode("idna").decode().lower()
            port = p.port
        except (ValueError, UnicodeError):
            return None
        if p.scheme not in {"http", "https"} or "." not in host or p.username or p.password:
            return None
        return urlunsplit((p.scheme, host + (f":{port}" if port else ""), p.path, p.query, ""))
