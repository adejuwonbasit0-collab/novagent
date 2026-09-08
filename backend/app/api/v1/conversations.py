from __future__ import annotations

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(desc(Conversation.last_message_at))
        .limit(limit)
    )
    result = await db.execute(query)
    conversations = result.scalars().all()

    outs = []
    for c in conversations:
        count_res = await db.execute(select(func.count(Message.id)).where(Message.conversation_id == c.id))
        msg_count = count_res.scalar_one() or 0
        outs.append(
            ConversationOut(
                id=c.id,
                title=c.title,
                is_archived=c.is_archived,
                last_message_at=c.last_message_at,
                created_at=c.created_at,
                message_count=msg_count,
            )
        )
    return outs


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = Conversation(
        user_id=current_user.id,
        title=payload.title,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    return ConversationOut(
        id=conv.id,
        title=conv.title,
        is_archived=conv.is_archived,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
        message_count=0,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
    )
    result = await db.execute(query)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages_out = [
        MessageOut(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            tool_calls_json=m.tool_calls_json,
            created_at=m.created_at,
        )
        for m in conv.messages
    ]

    return ConversationDetailOut(
        id=conv.id,
        title=conv.title,
        is_archived=conv.is_archived,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
        message_count=len(messages_out),
        messages=messages_out,
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conv.title = payload.title
    if payload.is_archived is not None:
        conv.is_archived = payload.is_archived
    await db.commit()
    await db.refresh(conv)

    count_res = await db.execute(select(func.count(Message.id)).where(Message.conversation_id == conv.id))
    msg_count = count_res.scalar_one() or 0

    return ConversationOut(
        id=conv.id,
        title=conv.title,
        is_archived=conv.is_archived,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
        message_count=msg_count,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    await db.delete(conv)
    await db.commit()
    return None


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def add_message_to_conversation(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    msg = Message(
        conversation_id=conv.id,
        role=payload.role,
        content=payload.content,
        tool_calls_json=payload.tool_calls_json,
    )
    db.add(msg)
    conv.last_message_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(msg)

    return MessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        role=msg.role,
        content=msg.content,
        tool_calls_json=msg.tool_calls_json,
        created_at=msg.created_at,
    )
