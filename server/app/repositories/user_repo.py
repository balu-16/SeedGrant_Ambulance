import uuid

from sqlalchemy import select

from app.models.user import Ambulance, User


async def get_user_by_id(db, uid: uuid.UUID):
    return (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()


async def get_user_by_email(db, email: str):
    return (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()


async def get_ambulance(db, aid: uuid.UUID):
    return (await db.execute(select(Ambulance).where(Ambulance.id == aid))).scalar_one_or_none()
