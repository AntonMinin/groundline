REWRITE_SYSTEM = (
    "You rewrite user questions into precise search queries for a document retrieval system. "
    "Expand abbreviations, resolve vague wording, keep key entities and terms, and keep the language of the question. "
    "If the question is already precise, return it unchanged. Return only the query text, nothing else."
)

SUFFICIENCY_SYSTEM = (
    "You judge whether the provided context contains enough information to answer the question. "
    'Respond with JSON only: {"sufficient": true|false, "missing": "<what information is missing, empty if sufficient>"}'
)

ANSWER_SYSTEM = (
    "You answer questions strictly based on the provided context fragments. "
    "Cite fragments inline using their numbers in square brackets, like [1] or [2][3]. "
    "If the context does not contain the answer, say so plainly and do not invent facts. "
    "Answer in the same language as the question."
)


def rewrite_messages(question: str, previous_query: str | None, missing: str | None) -> list[dict]:
    content = f"Question: {question}"
    if previous_query:
        content += f"\nPrevious search query: {previous_query}\nIt did not retrieve enough information. Missing: {missing}"
    return [{"role": "system", "content": REWRITE_SYSTEM}, {"role": "user", "content": content}]


def format_context(chunks) -> str:
    parts = []
    for number, chunk in enumerate(chunks, start=1):
        location = f"{chunk.filename}, chunk {chunk.chunk_index}" + (f", page {chunk.page}" if chunk.page else "")
        parts.append(f"[{number}] ({location})\n{chunk.content}")
    return "\n\n".join(parts)


def sufficiency_messages(question: str, chunks) -> list[dict]:
    return [
        {"role": "system", "content": SUFFICIENCY_SYSTEM},
        {"role": "user", "content": f"Question: {question}\n\nContext:\n{format_context(chunks)}"},
    ]


def answer_messages(question: str, chunks) -> list[dict]:
    return [
        {"role": "system", "content": ANSWER_SYSTEM},
        {"role": "user", "content": f"Context:\n{format_context(chunks)}\n\nQuestion: {question}"},
    ]
