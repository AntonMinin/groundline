from dataclasses import dataclass
from functools import lru_cache

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings

ENCODING = "cl100k_base"


@dataclass
class TextChunk:
    chunk_index: int
    page: int | None
    content: str


@lru_cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING)


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text, disallowed_special=()))


def chunk_pages(
    pages: list[tuple[int | None, str]],
    chunk_size: int = settings.chunk_size,
    chunk_overlap: int = settings.chunk_overlap,
) -> list[TextChunk]:
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=ENCODING, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks: list[TextChunk] = []
    for page, text in pages:
        for piece in splitter.split_text(text):
            if piece.strip():
                chunks.append(TextChunk(chunk_index=len(chunks), page=page, content=piece.strip()))
    return chunks
