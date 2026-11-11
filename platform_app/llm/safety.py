"""Defensive text redaction and citation checks at the sole model boundary."""

import hashlib
import json
import re
from collections.abc import Mapping

from pydantic import ValidationError


class GroundedLLMError(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code, self.detail = code, detail
        super().__init__(detail)


PRIVATE_FIELD = re.compile(r"(?:password|secret|token|api.?key|authorization|email|phone|address|customer|consumer|loyalty|person(?:al)?_?id)", re.I)
PERSONAL_FIELD = re.compile(r"(?:customer|consumer|loyalty|person(?:al)?_?id|email|phone|postal_address)", re.I)
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
CREDENTIAL = re.compile(r"(?i)\b(?:bearer\s+[A-Za-z0-9._~+/-]{8,}|sk-[A-Za-z0-9_-]{8,}|(?:api[_ -]?key|password|secret)\s*[:=]\s*[^\s,;]+)")
PHONE = re.compile(r"(?<![\w.])\+?\d[\d ()-]{9,}\d(?!\w|\.\d)")
UUID_ID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def redact(value, secrets=()):
    """Preserve aggregate numeric facts while removing contact fields and credentials."""
    if isinstance(value, Mapping):
        return {str(key): "[REDACTED]" if PRIVATE_FIELD.search(str(key)) else redact(item, secrets)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = EMAIL.sub("[EMAIL]", CREDENTIAL.sub("[CREDENTIAL]", value))
        # Keep machine references traceable when a UUID segment is all digits.
        # Known secret replacement above still takes precedence.
        return value if len(value) == 36 and UUID_ID.fullmatch(value) else PHONE.sub("[PHONE]", value)
    return value


def reject_personal_pricing(value):
    if isinstance(value, Mapping):
        if any(PERSONAL_FIELD.search(str(key)) for key in value):
            raise GroundedLLMError("personal_pricing_forbidden", "Only aggregate SKU-level pricing is supported.")
        for item in value.values():
            reject_personal_pricing(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_personal_pricing(item)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_citations(value: dict, supplied: set[str]):
    """Every emitted citation must refer to the actual supplied immutable chunk."""
    count = 0

    def walk(item):
        nonlocal count
        if isinstance(item, dict):
            for key, nested in item.items():
                if key == "citations":
                    if not isinstance(nested, list) or not nested or any(
                        not isinstance(citation, str) or citation not in supplied for citation in nested
                    ):
                        raise ValueError("Citations must identify supplied evidence.")
                    count += len(nested)
                else:
                    walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(value)
    if not count:
        raise ValueError("At least one evidence citation is required.")


def repair_feedback(error, schema) -> dict:
    """Return actionable validation locations/types, never raw output/input/context."""
    allowed_fields = set()
    def properties(value):
        if isinstance(value, dict):
            allowed_fields.update(value.get("properties", {}))
            for nested in value.values():
                properties(nested)
        elif isinstance(value, list):
            for nested in value:
                properties(nested)
    properties(schema.model_json_schema())
    if isinstance(error, ValidationError):
        return {"validation_errors": [{
            "loc": [part if isinstance(part, int) or part in allowed_fields else "[unknown_field]"
                    for part in item["loc"]], "type": item["type"]}
            for item in error.errors(include_input=False, include_context=False, include_url=False)[:20]]}
    if error.__class__.__name__ == "OutputParserException":
        return {"validation_errors": [{"loc": [], "type": "structured_output_parse_failed"}]}
    return {"validation_errors": [{"loc": ["citations"], "type": "supplied_citations_required"}]}
