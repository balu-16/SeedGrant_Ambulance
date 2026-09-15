"""Seed demo data: Benz Circle Vijayawada + approaches + device + driver + ambulance."""

import asyncio
import secrets

from sqlalchemy import select

import app.models  # noqa: F401
from app.core.dependencies import hash_api_key
from app.core.security import hash_password
from app.db.session import get_session_factory
from app.models.device import Device
from app.models.junction import Approach, Junction
from app.models.profile import DriverProfile
from app.models.user import Ambulance, User
from app.utils.geo import offset_point

BENZ_LAT, BENZ_LON = 16.5058, 80.6520


async def seed():
    factory = get_session_factory()
    async with factory() as db:
        j = (
            await db.execute(select(Junction).where(Junction.name == "Benz Circle, Vijayawada"))
        ).scalar_one_or_none()
        if not j:
            j = Junction(
                name="Benz Circle, Vijayawada",
                latitude=BENZ_LAT,
                longitude=BENZ_LON,
                radius_m=500.0,
            )
            db.add(j)
            await db.flush()
            windows = {
                "NORTH": (300, 60),
                "SOUTH": (120, 240),
                "EAST": (30, 150),
                "WEST": (210, 330),
            }
            entries = {
                "NORTH": (0, 150),
                "SOUTH": (180, 150),
                "EAST": (90, 150),
                "WEST": (270, 150),
            }
            for d, (lo, hi) in windows.items():
                b, dist = entries[d]
                elat, elon = offset_point(BENZ_LAT, BENZ_LON, b, dist)
                db.add(
                    Approach(
                        junction_id=j.id,
                        direction=d,
                        heading_min=lo,
                        heading_max=hi,
                        entry_lat=elat,
                        entry_lon=elon,
                    )
                )
        driver = (
            await db.execute(select(User).where(User.email == "driver@demo.io"))
        ).scalar_one_or_none()
        if not driver:
            driver = User(
                email="driver@demo.io", password_hash=hash_password("Demo123!"), role="driver"
            )
            db.add(driver)
            await db.flush()
        admin = (
            await db.execute(select(User).where(User.email == "admin@demo.io"))
        ).scalar_one_or_none()
        if not admin:
            admin = User(
                email="admin@demo.io", password_hash=hash_password("Admin123!"), role="admin"
            )
            db.add(admin)
            await db.flush()
        amb = (
            await db.execute(select(Ambulance).where(Ambulance.vehicle_no == "AP39-0001"))
        ).scalar_one_or_none()
        if not amb:
            amb = Ambulance(vehicle_no="AP39-0001", driver_id=driver.id)
            db.add(amb)
            await db.flush()
        prof = (
            await db.execute(select(DriverProfile).where(DriverProfile.user_id == driver.id))
        ).scalar_one_or_none()
        if not prof:
            db.add(
                DriverProfile(
                    user_id=driver.id,
                    name="Rohit Sharma",
                    phone="+91 90000 00124",
                    region="Bandra West, Mumbai",
                    hospital="Bhabha Hospital, Bandra",
                    control_center="Mumbai Traffic Control",
                )
            )
        dev = (
            await db.execute(select(Device).where(Device.junction_id == j.id))
        ).scalar_one_or_none()
        raw = None
        if not dev:
            raw = secrets.token_hex(24)
            dev = Device(junction_id=j.id, name="PI-BENZ-01", api_key_hash=hash_api_key(raw))
            db.add(dev)
        await db.commit()
        print(f"Seeded junction={j.id} ambulance={amb.id} driver={driver.email}")
        if raw:
            print(f"DEVICE_API_KEY (save now, shown once)={raw}")


if __name__ == "__main__":
    asyncio.run(seed())
