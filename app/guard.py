import re
import unicodedata

from app.config import settings

MAX_QUESTION_CHARS = 2000
MAX_MODEL_TEXT_CHARS = 500
MAX_MISSING_CHARS = 200
MAX_FILENAME_LABEL_CHARS = 200

FENCE_TAGS = ("context", "fragment", "user_question")

_INVISIBLE = re.compile(
    "[­؜᠎​-‏‪-‮⁠-⁤⁦-⁯﻿\U000e0000-\U000e007f]"
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_BLANK_LINES = re.compile(r"\n{3,}")

_REDACTIONS = (
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"), "[SECRET]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "[SECRET]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[SECRET]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[SECRET]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[IBAN]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), "[CARD]"),
    (re.compile(r"\+\d[\d\s().-]{7,}\d"), "[PHONE]"),
)


class UnsafeInput(ValueError):
    pass


def clean(text: str) -> str:
    return _CONTROL.sub("", unicodedata.normalize("NFKC", _INVISIBLE.sub("", text)))


def neutralize(text: str) -> str:
    for tag in FENCE_TAGS:
        text = text.replace(f"<{tag}", "&lt;" + tag).replace(f"</{tag}", "&lt;/" + tag)
    return text


def sanitize_question(text: str) -> str:
    question = _BLANK_LINES.sub("\n\n", clean(text)).strip()
    if not question:
        raise UnsafeInput("Question is empty after normalisation")
    if len(question) > MAX_QUESTION_CHARS:
        raise UnsafeInput(f"Question is longer than {MAX_QUESTION_CHARS} characters after normalisation")
    return neutralize(question)


def sanitize_filename(filename: str) -> str:
    name = " ".join(clean(filename).replace("\\", "/").split("/")[-1].split()).strip(". ")
    if not name:
        raise UnsafeInput("File name is empty after normalisation")
    return name


def clamp(text: str, limit: int = MAX_MODEL_TEXT_CHARS) -> str:
    return neutralize(clean(text)[:limit]).strip()


def redact(text: str) -> str:
    if not settings.telemetry_redaction:
        return text
    for pattern, placeholder in _REDACTIONS:
        text = pattern.sub(placeholder, text)
    return text


def redact_value(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    return value


def mask_telemetry(*, data, **kwargs):
    return redact_value(data)
