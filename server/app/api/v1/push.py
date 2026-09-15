"""Push-token registration for the driver mobile app.

RN flow: login → OS permission prompt (expo-notifications) → POST /push/register.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.dependencies import get_current_user, get_db
from app.core.exceptions import Conflict, NotFound
from app.models.device import PushSubscription

router = APIRouter(prefix="/push", tags=["push"])


class PushRegisterIn(BaseModel):
    player_id: str = Field(min_length=1, max_length=128)
    expo_push_token: str = Field(default="", max_length=128)
    device_type: str = Field(default="", max_length=32)
    app_version: str = Field(default="", max_length=32)


@router.post("/register")
async def register_push(body: PushRegisterIn, db=Depends(get_db), user=Depends(get_current_user)):
    # Expo token preferred when supplied; player_id kept for backwards compat.
    token = body.expo_push_token.strip() or body.player_id
    expo_token = body.expo_push_token.strip() or None
    existing = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.player_id == token)
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if existing:
        if existing.user_id != user.id:
            # token is bound to another account — generic message avoids
            # confirming token existence across accounts.
            raise Conflict("Unable to register push token")
        # same user re-registering: idempotent refresh of device metadata
        existing.expo_push_token = expo_token
        existing.device_type = body.device_type
        existing.app_version = body.app_version
        existing.last_seen_at = now
    else:
        db.add(
            PushSubscription(
                user_id=user.id,
                player_id=token,
                expo_push_token=expo_token,
                device_type=body.device_type,
                app_version=body.app_version,
                last_seen_at=now,
            )
        )
    try:
        await db.commit()
    except IntegrityError:
        # concurrent registration of the same token lost the unique race
        await db.rollback()
        raise Conflict("Unable to register push token") from None
    return {"success": True, "data": {"registered": True, "player_id": token}}


@router.get("")
async def list_push(
    limit: int = Query(default=100, ge=1, le=500),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    rows = (
        (
            await db.execute(
                select(PushSubscription)
                .where(PushSubscription.user_id == user.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "success": True,
        "data": [
            {
                "player_id": r.player_id,
                "device_type": r.device_type,
                "last_seen": r.last_seen_at.isoformat() if r.last_seen_at else None,
            }
            for r in rows
        ],
    }


@router.delete("/{player_id}")
async def unregister_push(player_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.player_id == player_id, PushSubscription.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise NotFound("Push subscription not found")
    await db.delete(row)
    await db.commit()
    return {"success": True, "data": {"removed": True}}
