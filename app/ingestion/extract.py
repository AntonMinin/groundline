from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.config import settings

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


class UnsupportedFileError(Exception):
    pass


class InvalidFileError(Exception):
    pass


def check_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileError(f"Unsupported file type '{extension}', allowed: pdf, txt, md")
    return extension


def _too_long() -> InvalidFileError:
    return InvalidFileError(f"The document holds more than {settings.max_document_chars:,} characters of text")


def _read_pdf(source) -> list[tuple[int | None, str]]:
    try:
        reader = PdfReader(source)
        if len(reader.pages) > settings.max_pdf_pages:
            raise InvalidFileError(f"The PDF has more than {settings.max_pdf_pages} pages")
        pages, total = [], 0
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            total += len(text)
            if total > settings.max_document_chars:
                raise _too_long()
            pages.append((number, text))
        return pages
    except (PyPdfError, ValueError, KeyError, OSError) as exc:
        raise InvalidFileError(f"Cannot parse PDF: {exc}") from exc


def _decode(data: bytes) -> list[tuple[int | None, str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidFileError("Text file must be UTF-8 encoded") from exc
    if len(text) > settings.max_document_chars:
        raise _too_long()
    return [(None, text)]


def extract_pages(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    extension = check_extension(filename)
    if not data:
        raise InvalidFileError("File is empty")
    return _read_pdf(BytesIO(data)) if extension == ".pdf" else _decode(data)


def extract_pages_from_path(filename: str, path: str) -> list[tuple[int | None, str]]:
    extension = check_extension(filename)
    if Path(path).stat().st_size == 0:
        raise InvalidFileError("File is empty")
    return _read_pdf(path) if extension == ".pdf" else _decode(Path(path).read_bytes())
