from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.config import settings
from app.ingestion import extract


def blank_pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(100, 100)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class Page:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self) -> str:
        return self.text


class Reader:
    extracted = 0

    def __init__(self, source):
        self.pages = [Page("x" * 400) for _ in range(10)]
        for page in self.pages:
            original = page.extract_text

            def counted(original=original):
                Reader.extracted += 1
                return original()

            page.extract_text = counted


def test_a_pdf_with_too_many_pages_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "max_pdf_pages", 3)
    with pytest.raises(extract.InvalidFileError, match="more than 3 pages"):
        extract.extract_pages("big.pdf", blank_pdf(4))
    assert len(extract.extract_pages("ok.pdf", blank_pdf(3))) == 3


def test_pdf_text_stops_being_extracted_once_it_is_too_long(monkeypatch):
    monkeypatch.setattr(settings, "max_document_chars", 1000)
    monkeypatch.setattr(extract, "PdfReader", Reader)
    Reader.extracted = 0
    with pytest.raises(extract.InvalidFileError, match="more than 1,000 characters"):
        extract.extract_pages("dense.pdf", b"%PDF-1.4")
    assert Reader.extracted == 3


def test_a_text_file_over_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "max_document_chars", 10)
    with pytest.raises(extract.InvalidFileError, match="more than 10 characters"):
        extract.extract_pages("notes.md", b"x" * 11)
    assert extract.extract_pages("notes.md", b"x" * 10) == [(None, "x" * 10)]
