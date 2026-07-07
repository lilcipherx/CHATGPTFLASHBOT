"""Admin CRM: free-text notes and tags on a user (ТЗ §9).

Reads and most mutations are gated to support staff (the lowest tier — they work
the user cards day to day); deleting a note is admin-only. All mutations are
audited.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser
from core.models.crm import UserNote, UserTag

router = APIRouter(prefix="/crm", tags=["admin-crm"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _note_dict(n: UserNote) -> dict:
    return {
        "id": n.id, "user_id": n.user_id, "admin_id": n.admin_id, "text": n.text,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/users/{user_id}")
async def get_user_crm(
    user_id: int,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    notes = (await session.scalars(
        select(UserNote).where(UserNote.user_id == user_id).order_by(UserNote.id.desc())
    )).all()
    tags = (await session.scalars(
        select(UserTag).where(UserTag.user_id == user_id).order_by(UserTag.tag)
    )).all()
    return {"notes": [_note_dict(n) for n in notes], "tags": [t.tag for t in tags]}


class NoteCreate(BaseModel):
    text: str = Field(..., max_length=4000)  # FIX: AUDIT13-L17


@router.post("/users/{user_id}/notes")
async def add_note(
    user_id: int, req: NoteCreate, request: Request,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty note")
    note = UserNote(user_id=user_id, admin_id=admin.id, text=text)
    session.add(note)
    await audit(session, admin_id=admin.id, action="crm.note.add", target_type="user",
    target_id=str(user_id), after={"note_id": note.id}, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return _note_dict(note)


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    note = await session.get(UserNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="not found")
    user_id = note.user_id
    await session.delete(note)
    await audit(session, admin_id=admin.id, action="crm.note.delete", target_type="user",
    target_id=str(user_id), after={"note_id": note_id}, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True}


class TagCreate(BaseModel):
    tag: str = Field(..., max_length=40)  # FIX: AUDIT13-L17


@router.post("/users/{user_id}/tags")
async def add_tag(
    user_id: int, req: TagCreate, request: Request,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tag = req.tag.strip()
    if not tag:
        raise HTTPException(status_code=400, detail="empty tag")
    tag = tag[:40]
    session.add(UserTag(user_id=user_id, tag=tag))
    try:
        await session.commit()
    except IntegrityError:
        # Duplicate (user_id, tag) — idempotent: treat as success.
        await session.rollback()
        return {"ok": True, "tag": tag}
    await audit(session, admin_id=admin.id, action="crm.tag.add", target_type="user",
                target_id=str(user_id), after={"tag": tag}, ip=_ip(request))
    return {"ok": True, "tag": tag}


@router.delete("/users/{user_id}/tags/{tag}")
async def delete_tag(
    user_id: int, tag: str, request: Request,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = (await session.scalars(
        select(UserTag).where(UserTag.user_id == user_id, UserTag.tag == tag)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    await session.delete(row)
    await audit(session, admin_id=admin.id, action="crm.tag.delete", target_type="user",
    target_id=str(user_id), after={"tag": tag}, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True}
