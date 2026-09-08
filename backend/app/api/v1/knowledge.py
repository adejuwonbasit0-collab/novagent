import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.knowledge import (
    MAX_DOCUMENTS_PER_USER,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
)
from app.models.user import User
from app.schemas.knowledge import KnowledgeDocumentOut, KnowledgeTextCreate
from app.services.knowledge_retrieval import chunk_text

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

# Deliberately small, honest set of supported types for this MVP -- see
# knowledge_retrieval.py's module docstring for why this doesn't do
# PDF/DOCX yet: those need new parsing dependencies (pypdf/python-docx)
# this codebase doesn't have, and per spec section 47, returning a clear
# 415 for an unsupported type beats silently mishandling binary content
# as if it were text (which is what naively decoding a .pdf as UTF-8
# would actually do -- produce garbage chunks that look like they worked).
_SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".csv"}
MAX_UPLOAD_BYTES = 2_000_000  # 2MB of text is already a lot of chunks at this MVP's per-user cap


async def _document_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.user_id == user_id)
    )
    return result.scalar_one()


async def _ingest(db: AsyncSession, user: User, title: str, filename: str | None, text: str) -> KnowledgeDocument:
    document = KnowledgeDocument(
        user_id=user.id,
        title=title,
        source_filename=filename,
        status=KnowledgeDocumentStatus.PROCESSING,
        char_count=len(text),
    )
    db.add(document)
    await db.flush()  # assigns document.id without committing yet

    try:
        pieces = chunk_text(text)
        if not pieces:
            document.status = KnowledgeDocumentStatus.FAILED
            document.error = "No readable text content found."
        else:
            for i, piece in enumerate(pieces):
                db.add(KnowledgeChunk(document_id=document.id, user_id=user.id, chunk_index=i, content=piece))
            document.status = KnowledgeDocumentStatus.READY
            document.chunk_count = len(pieces)
    except Exception as e:  # processing is synchronous today -- a failure here must not lose the document
        document.status = KnowledgeDocumentStatus.FAILED
        document.error = str(e)

    await db.commit()
    await db.refresh(document)
    return document


@router.post("/documents/text", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
async def create_text_document(
    payload: KnowledgeTextCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if await _document_count(db, user.id) >= MAX_DOCUMENTS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You've reached the {MAX_DOCUMENTS_PER_USER}-document limit. Delete something first.",
        )
    return await _ingest(db, user, payload.title, None, payload.content)


@router.post("/documents", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if await _document_count(db, user.id) >= MAX_DOCUMENTS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You've reached the {MAX_DOCUMENTS_PER_USER}-document limit. Delete something first.",
        )

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"'{ext or 'unknown'}' isn't supported yet — only .txt, .md, and .csv for now. "
            "PDF/DOCX support hasn't been built.",
        )

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES} byte limit.",
        )
    if len(contents) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Couldn't read this as UTF-8 text — is it actually a text file?",
        )

    title = file.filename or "Untitled"
    return await _ingest(db, user, title, file.filename, text)


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
async def list_documents(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.user_id == user.id).order_by(KnowledgeDocument.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.user_id == user.id)
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Explicit delete rather than relying only on the FK's ondelete=CASCADE:
    # SQLite only enforces ON DELETE CASCADE when foreign_keys=ON is set on
    # the connection, which isn't guaranteed for every SQLite setup this
    # project's DATABASE_URL might point at -- doing it explicitly here
    # works identically on both database backends regardless of that
    # pragma, rather than silently leaving orphaned chunks on SQLite.
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
    await db.delete(document)
    await db.commit()
