"""Emergency contacts (SOS recipients) — user-scoped, max 5, full-list replace."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select

from app.api.v1.devices import _audit
from app.core.dependencies import get_current_user, get_db
from app.core.exceptions import NotFound
from app.models.contact import DriverContact
from app.models.user import User
from app.schemas.common import ContactsPutIn

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _contact_out(c: DriverContact) -> dict:
    return {"id": str(c.id), "name": c.name, "phone": c.phone, "position": c.position}


@router.get("")
async def list_contacts(db=Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        (
            await db.execute(
                select(DriverContact)
                .where(DriverContact.user_id == user.id)
                .order_by(DriverContact.position, DriverContact.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {"success": True, "data": [_contact_out(c) for c in rows]}


@router.put("")
async def replace_contacts(
    body: ContactsPutIn, db=Depends(get_db), user: User = Depends(get_current_user)
):
    """Full-list replace (idempotent sync primitive for the app)."""
    await db.execute(delete(DriverContact).where(DriverContact.user_id == user.id))
    for i, c in enumerate(body.contacts):
        db.add(DriverContact(user_id=user.id, name=c.name, phone=c.phone, position=i))
    _audit(
        db, str(user.id), "contacts.replace", "emergency_contacts", {"count": len(body.contacts)}
    )
    await db.commit()
    rows = (
        (
            await db.execute(
                select(DriverContact)
                .where(DriverContact.user_id == user.id)
                .order_by(DriverContact.position, DriverContact.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {"success": True, "data": [_contact_out(c) for c in rows]}


@router.delete("/{cid}")
async def delete_contact(
    cid: uuid.UUID, db=Depends(get_db), user: User = Depends(get_current_user)
):
    c = (
        await db.execute(
            select(DriverContact).where(
                DriverContact.id == cid, DriverContact.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if not c:
        raise NotFound("Contact not found")
    await db.delete(c)
    await db.commit()
    return {"success": True, "data": {"deleted": True}}
