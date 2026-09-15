from app.ingestion.chunking import chunk_pages, count_tokens
from app.ingestion.extract import InvalidFileError, UnsupportedFileError, extract_pages

import pytest


def _long_text(words: int) -> str:
    return " ".join(f"word{i}" for i in range(words))


def test_chunks_respect_size_and_overlap():
    chunks = chunk_pages([(1, _long_text(3000))], chunk_size=700, chunk_overlap=100)
    assert len(chunks) > 1
    assert all(count_tokens(chunk.content) <= 700 for chunk in chunks)
    first_tail = chunks[0].content.split()[-20:]
    assert " ".join(first_tail) in chunks[1].content


def test_chunks_keep_page_numbers_and_global_index():
    chunks = chunk_pages([(1, "alpha " * 50), (2, ""), (3, "gamma " * 50)])
    assert [chunk.page for chunk in chunks] == [1, 3]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]


def test_text_file_extraction():
    assert extract_pages("notes.md", "# Title\nbody".encode()) == [(None, "# Title\nbody")]


def test_rejects_unsupported_extension():
    with pytest.raises(UnsupportedFileError):
        extract_pages("image.png", b"data")


def test_rejects_broken_pdf_and_empty_file():
    with pytest.raises(InvalidFileError):
        extract_pages("broken.pdf", b"not a pdf")
    with pytest.raises(InvalidFileError):
        extract_pages("empty.txt", b"")
