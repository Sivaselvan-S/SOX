import re

BEARER_TOKEN_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{15,}")
API_KEY_PATTERN = re.compile(r"(sk-[a-zA-Z0-9]{20,})")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")


class TelemetrySanitizer:
    """In-flight PII and credential scrubber for event payloads."""

    @classmethod
    def scrub(cls, payload: str) -> str:
        if not payload:
            return payload

        # Replace Bearer tokens
        sanitized = BEARER_TOKEN_PATTERN.sub(r"\1[REDACTED_TOKEN]", payload)
        # Replace API keys
        sanitized = API_KEY_PATTERN.sub(r"[REDACTED_API_KEY]", sanitized)
        # Replace Emails
        sanitized = EMAIL_PATTERN.sub(r"[REDACTED_EMAIL]", sanitized)

        return sanitized
