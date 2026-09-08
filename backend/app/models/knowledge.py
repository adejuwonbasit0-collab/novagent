from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, Text
from sqlalchemy import UUID  # generic 2.0 type -- native UUID on postgres, CHAR(32) elsewhere, so sqlite works for local dev too
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

# Per-user caps, enforced in the router (api/v1/knowledge.py) and the
# retrieval service (services/knowledge_retrieval.py) -- this is a
# keyword-scored MVP (see the module docstring in knowledge_retrieval.py
# for why, and what upgrading to real embeddings would need), and that
# approach means every search scans up to this many chunks in Python. Caps
# keep that bounded and predictable rather than degrading silently as a
# user's knowledge base grows.
MAX_DOCUMENTS_PER_USER = 200
MAX_CHUNKS_PER_USER = 20000


class KnowledgeDocumentStatus(str, enum.Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class KnowledgeDocument(UUIDPKMixin, TimestampMixin, Base):
    """
    Spec section 33. A single uploaded/pasted source (one .txt/.md/.csv
    file, or one pasted block of text) that's been split into
    KnowledgeChunk rows for retrieval. Processing is synchronous today
    (see the router) -- status/error columns exist for when that becomes
    a background job, and so the dashboard always has something honest to
    show rather than a document just vanishing on failure.
    """

    __tablename__ = "knowledge_documents"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[KnowledgeDocumentStatus] = mapped_column(
        SAEnum(KnowledgeDocumentStatus, name="knowledge_document_status"),
        default=KnowledgeDocumentStatus.PROCESSING,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgeChunk(UUIDPKMixin, TimestampMixin, Base):
    """
    user_id is denormalized from the parent document (not just derived via
    a join) deliberately -- every retrieval query in
    knowledge_retrieval.py filters on KnowledgeChunk.user_id directly, the
    same "never trust a join alone for a user-isolation boundary, filter
    the row you're actually reading" pattern used for pending tool calls
    (app/tools/base.py) and reminders elsewhere in this codebase.
    """

    __tablename__ = "knowledge_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
