from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


class UnsupportedFileError(Exception):
    pass


class InvalidFileError(Exception):
    pass


def extract_pages(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileError(f"Unsupported file type '{extension}', allowed: pdf, txt, md")
    if not data:
        raise InvalidFileError("File is empty")
    if extension == ".pdf":
        try:
            reader = PdfReader(BytesIO(data))
            return [(number, page.extract_text() or "") for number, page in enumerate(reader.pages, start=1)]
        except (PyPdfError, ValueError, KeyError) as exc:
            raise InvalidFileError(f"Cannot parse PDF: {exc}") from exc
    try:
        return [(None, data.decode("utf-8-sig"))]
    except UnicodeDecodeError as exc:
        raise InvalidFileError("Text file must be UTF-8 encoded") from exc
