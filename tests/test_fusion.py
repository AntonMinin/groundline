import uuid

from app.retrieval.fusion import RetrievedChunk, reciprocal_rank_fusion


def _chunk(name: str) -> RetrievedChunk:
    return RetrievedChunk(
        id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        document_id=uuid.uuid4(),
        filename=f"{name}.md",
        chunk_index=0,
        page=None,
        content=name,
    )


def test_chunk_found_by_both_searches_ranks_first():
    a, b, c, d = (_chunk(name) for name in "abcd")
    fused = reciprocal_rank_fusion([[a, b, c], [d, c, a]])
    assert [chunk.content for chunk in fused][:2] == ["a", "c"]


def test_fusion_deduplicates_and_scores():
    a, b = _chunk("a"), _chunk("b")
    fused = reciprocal_rank_fusion([[a, b], [a]])
    assert [chunk.content for chunk in fused] == ["a", "b"]
    assert fused[0].score == 2 / 61
    assert fused[1].score == 1 / 62


def test_fusion_handles_empty_lists():
    assert reciprocal_rank_fusion([[], []]) == []
