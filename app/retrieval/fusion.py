from dataclasses import dataclass, replace
from uuid import UUID


@dataclass(frozen=True)
class RetrievedChunk:
    id: UUID
    document_id: UUID
    filename: str
    chunk_index: int
    page: int | None
    content: str
    score: float = 0.0

    def source(self) -> dict:
        return {
            "document_id": str(self.document_id),
            "filename": self.filename,
            "chunk_index": self.chunk_index,
            "page": self.page,
        }


def reciprocal_rank_fusion(result_lists: list[list[RetrievedChunk]], k: int = 60) -> list[RetrievedChunk]:
    scores: dict[UUID, float] = {}
    chunks: dict[UUID, RetrievedChunk] = {}
    for results in result_lists:
        for rank, chunk in enumerate(results, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            chunks.setdefault(chunk.id, chunk)
    ordered = sorted(scores, key=scores.__getitem__, reverse=True)
    return [replace(chunks[chunk_id], score=scores[chunk_id]) for chunk_id in ordered]
