from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeChunk, MAX_CHUNKS_PER_USER

# ---------------------------------------------------------------------------
# Design note, read before "improving" this into a vector search: this is a
# deliberately simple keyword-overlap scorer, not semantic/embedding search.
#
# Why: this backend supports DATABASE_URL pointing at either Postgres OR
# SQLite (see backend/.env.example and models/mixins.py's UUID type comment
# -- SQLite is the explicit no-Docker local dev path). A real embedding
# pipeline needs (a) a vector column type -- pgvector on Postgres has no
# SQLite equivalent, so the two dev paths would need genuinely different
# storage -- and (b) an embedding API call per chunk at ingest time and per
# query at search time, on a provider that actually offers embeddings
# (Anthropic's API, this project's default provider, does not). Either of
# those is a real, substantial addition, not a drop-in swap.
#
# What this does instead: score every one of the user's chunks by how many
# of the query's significant words it contains, weighted by how rare that
# word is across the user's own chunks (a simplified TF-IDF), and return the
# top matches. It will correctly find a document that shares vocabulary with
# the query ("What does my lease say about pets?" against a chunk containing
# "pets are not permitted") and will NOT find a conceptual match with no
# shared words ("Am I allowed to have a dog?" against that same chunk,
# unless "dog" and "pets" both appear somewhere). That's a real, known
# limitation of this MVP, not a bug -- upgrading it later means adding a
# vector column + embedding calls, not touching the ingest/chunking side.
# ---------------------------------------------------------------------------

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
_MIN_CHUNK_FRACTION = 0.5  # a break point closer to `start` than this fraction of chunk_size is rejected
TOP_K = 5
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "to", "of", "and", "or",
    "in", "on", "at", "for", "with", "about", "as", "by", "this", "that", "it", "my", "me", "i",
    "what", "does", "do", "did", "have", "has", "had", "can", "could", "would", "should", "will",
}


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Fixed-size chunking with overlap, breaking on paragraph/sentence
    boundaries where possible rather than mid-word, so a chunk reads as a
    coherent unit to the model rather than an arbitrary character slice.

    BUG FOUND BY ACTUALLY RUNNING THIS (not just reading it): the first
    version of this function accepted ANY rfind() break point in
    (start, end], including one just a few characters after start. On
    text with short, repetitive sentences (". " appearing every ~15
    chars -- not a contrived case, e.g. a bullet list or short-line CSV
    dump), that produced a cascade of shrinking near-empty chunks (52
    chunks for input that should have been ~2, sizes trailing off
    494, 304, 48, 47, 46, ... down to 1 character) because each break
    point landed close to the previous start and barely advanced. Fixed
    by only honoring a break point that keeps the chunk at least
    MIN_CHUNK_FRACTION of the target size -- otherwise it hard-cuts at
    chunk_size instead, same as it always did for text with no
    convenient boundary nearby.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    min_chunk_len = int(chunk_size * _MIN_CHUNK_FRACTION)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            best_break = -1
            for boundary in ("\n\n", ". ", " "):
                candidate = text.rfind(boundary, start, end)
                if candidate != -1 and candidate - start >= min_chunk_len:
                    best_break = candidate + len(boundary)
                    break
            if best_break != -1:
                end = best_break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        # Always advance by at least min_chunk_len regardless of `overlap`,
        # so a caller passing overlap >= chunk_size (which the pathological
        # test above deliberately does) can't stall progress into a long
        # run of near-duplicate one-character-apart chunks either -- it
        # still terminates in O(len(text) / chunk_size) chunks, not
        # O(len(text)).
        start = max(end - overlap, start + min_chunk_len)
    return chunks


def _tokenize(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1]


async def search_knowledge(db: AsyncSession, user_id: uuid.UUID, query: str, top_k: int = TOP_K) -> list[dict]:
    """Returns up to top_k {content, document_id} dicts, highest-scoring
    first. Empty list if the user has no chunks or nothing scores above
    zero shared terms -- callers should treat that as "nothing relevant
    found", not an error."""
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    result = await db.execute(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.user_id == user_id)
        .order_by(KnowledgeChunk.created_at.desc())
        .limit(MAX_CHUNKS_PER_USER)
    )
    chunks = result.scalars().all()
    if not chunks:
        return []

    # document frequency across this user's own chunks -- a term that
    # appears in nearly every chunk (e.g. the user's own name, if every
    # document happens to mention it) contributes less to a match than one
    # that appears in only a few, same idea as IDF in TF-IDF.
    doc_freq: dict[str, int] = {}
    tokenized_chunks: list[tuple[KnowledgeChunk, list[str]]] = []
    for chunk in chunks:
        tokens = _tokenize(chunk.content)
        tokenized_chunks.append((chunk, tokens))
        for term in set(tokens):
            doc_freq[term] = doc_freq.get(term, 0) + 1

    n_chunks = len(chunks)
    scored: list[tuple[float, KnowledgeChunk]] = []
    for chunk, tokens in tokenized_chunks:
        if not tokens:
            continue
        term_counts: dict[str, int] = {}
        for t in tokens:
            term_counts[t] = term_counts.get(t, 0) + 1
        score = 0.0
        for term in query_terms:
            tf = term_counts.get(term, 0)
            if tf == 0:
                continue
            # +1 smoothing so a term appearing in every single chunk still
            # contributes a small positive score rather than being zeroed out
            idf = 1.0 + (n_chunks / (1.0 + doc_freq.get(term, 0)))
            score += tf * idf
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{"content": c.content, "document_id": str(c.document_id)} for _, c in scored[:top_k]]
