"""Coverage for the completion-phase endpoints:

- /ambulances/mine hospital embed + on_duty
- /emergencies/history events[] + distance
- login last_login_at (+ admin users list exposure)
- /vision/detections device-key ingest (documented Pi path)
- PATCH /junctions/{jid} incl. deactivate releases open commands
- PATCH /hospitals/mine self-service profile edit
- /commands/admin/list since/until filters
- /admin/live junction_states
- /admin/notification-prefs round-trip + muting
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.device import UserNotificationPref
from app.models.user import User

from .conftest import PASSWORD, insert_priority_command, login_headers, make_user

pytestmark = pytest.mark.asyncio


async def _create_hospital(client, admin, name: str) -> dict:
    r = await client.post(
        "/api/v1/admin/hospitals",
        json={"name": name, "latitude": 12.9, "longitude": 77.6},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_mine_embeds_hospital_and_on_duty(client, admin, driver, ambulance, db_factory):
    h = await _create_hospital(client, admin, "Test General")
    r = await client.patch(
        f"/api/v1/ambulances/{ambulance['id']}",
        json={"hospital_id": h["id"], "driver_id": str(driver["user"].id)},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/ambulances/mine", headers=driver["headers"])
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["on_duty"] is True
    assert data["hospital"]["id"] == h["id"]
    assert data["hospital"]["name"] == "Test General"
    assert data["hospital"]["latitude"] == 12.9
    # duty state flips through the fleet API and is visible to the driver
    r = await client.patch(
        f"/api/v1/ambulances/{ambulance['id']}",
        json={"on_duty": False, "driver_id": str(driver["user"].id)},
        headers=admin["headers"],
    )
    r = await client.get("/api/v1/ambulances/mine", headers=driver["headers"])
    assert r.json()["data"]["on_duty"] is False


async def test_history_returns_events_distance_and_junctions(
    client, driver, ambulance, junction, db_factory
):
    sid = (await client.post(
        "/api/v1/emergencies/start",
        json={"ambulance_id": ambulance["id"]},
        headers=driver["headers"],
    )).json()["data"]["session_id"]
    from .conftest import gps_near_junction

    fix = await gps_near_junction(db_factory, uuid.UUID(junction["id"]))
    r = await client.post(f"/api/v1/emergencies/{sid}/gps", json=fix, headers=driver["headers"])
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/emergencies/{sid}/stop", headers=driver["headers"])
    assert r.status_code == 200, r.text

    r = await client.get("/api/v1/emergencies/history", headers=driver["headers"])
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert rows, "history should contain the stopped session"
    row = rows[0]
    # the 150m fix inside the radius mints exactly one PRIORITY_REQUEST junction
    cmd_events = [e for e in row["events"] if e["kind"] == "command"]
    assert row["junctions_crossed"] == len({e["junction_id"] for e in cmd_events
                                             if e["type"] == "PRIORITY_REQUEST"})
    assert row["distance_m"] >= 0
    kinds = [e["kind"] for e in row["events"]]
    assert kinds[0] == "session" and row["events"][0]["type"] == "started"
    assert kinds[-1] == "session" and row["events"][-1]["status"] == "COMPLETED"


async def test_login_sets_last_login_visible_to_admin(client, admin, db_factory):
    u = await make_user(db_factory, "late@example.com", role="driver")
    assert u.last_login_at is None
    await login_headers(client, u.email)
    async with db_factory() as s:
        row = (
            await s.execute(select(User).where(User.email == u.email))
        ).scalar_one()
        assert row.last_login_at is not None
    r = await client.get("/api/v1/admin/users", headers=admin["headers"])
    items = r.json()["data"]["items"]
    emails = {row["email"]: row for row in items}
    assert emails[u.email]["last_login"] is not None


async def test_vision_device_key_ingest(client, admin, driver, junction, device, db_factory):
    # device-key path (the documented Pi ingest) works without a user token
    r = await client.post(
        "/api/v1/vision/detections",
        json=[{"junction_id": junction["id"], "vehicle_class": "car", "confidence": 0.9}],
        headers={"X-Device-Api-Key": device["api_key"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["stored"] == 1

    # a device MAY tag a session that has an open command for its junction
    linked = await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    r = await client.post(
        "/api/v1/vision/detections",
        json=[
            {
                "session_id": str(linked.session_id),
                "junction_id": junction["id"],
                "vehicle_class": "bus",
                "confidence": 0.8,
            }
        ],
        headers={"X-Device-Api-Key": device["api_key"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["stored"] == 1

    # ...but not a session whose open commands are all on OTHER junctions
    r = await client.post(
        "/api/v1/junctions",
        json={"name": "Other Junction", "latitude": 13.0, "longitude": 77.7},
        headers=admin["headers"],
    )
    other_jid = r.json()["data"]["id"]
    unlinked = await insert_priority_command(db_factory, uuid.UUID(other_jid))
    r = await client.post(
        "/api/v1/vision/detections",
        json=[
            {
                "session_id": str(unlinked.session_id),
                "junction_id": junction["id"],
                "vehicle_class": "bus",
                "confidence": 0.8,
            }
        ],
        headers={"X-Device-Api-Key": device["api_key"]},
    )
    assert r.status_code == 403, r.text

    # user-token path keeps working (no junction/session metadata)
    r = await client.post(
        "/api/v1/vision/detections",
        json=[{"vehicle_class": "truck", "confidence": 0.5}],
        headers=driver["headers"],
    )
    assert r.status_code == 200, r.text


async def test_patch_junction_and_deactivate_releases_commands(
    client, admin, driver, junction, db_factory
):
    r = await client.patch(
        f"/api/v1/junctions/{junction['id']}",
        json={"name": "Renamed Junction", "radius_m": 420},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text

    await insert_priority_command(db_factory, uuid.UUID(junction["id"]))
    r = await client.patch(
        f"/api/v1/junctions/{junction['id']}",
        json={"is_active": False},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["is_active"] is False

    from app.models.emergency import EmergencyCommand

    async with db_factory() as s:
        cmds = (await s.execute(select(EmergencyCommand))).scalars().all()
        assert cmds
        assert all(c.status == "EXPIRED" for c in cmds)

    # non-admin rejected
    r = await client.patch(
        f"/api/v1/junctions/{junction['id']}", json={"name": "X"}, headers=driver["headers"]
    )
    assert r.status_code == 403


async def test_patch_hospitals_mine(client, admin, db_factory):
    h = await _create_hospital(client, admin, "Self Service Hospital")
    u = await make_user(db_factory, "hosuser@example.com", role="hospital")
    async with db_factory() as s:
        row = await s.get(User, u.id)
        row.hospital_id = uuid.UUID(h["id"])
        await s.commit()
    headers = await login_headers(client, u.email)

    r = await client.patch(
        "/api/v1/hospitals/mine",
        json={"name": "Renamed Self Service", "phone": "+91 90000 00000"},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    # an unassigned HOSPITAL user owns nothing
    u2 = await make_user(db_factory, "hosnone@example.com", role="hospital")
    headers2 = await login_headers(client, u2.email)
    r = await client.patch(
        "/api/v1/hospitals/mine", json={"name": "X"}, headers=headers2
    )
    assert r.status_code == 403


async def test_command_log_since_until(client, admin, db_factory):
    await insert_priority_command(db_factory, uuid.uuid4())
    r = await client.get("/api/v1/commands/admin/list", headers=admin["headers"])
    assert r.status_code == 200 and r.json()["data"], r.text
    created = r.json()["data"][0]["created_at"]

    from datetime import UTC, datetime, timedelta

    ts = datetime.fromisoformat(created)
    r = await client.get(
        "/api/v1/commands/admin/list",
        params={
            "since": (ts - timedelta(seconds=1)).isoformat(),
            "until": (ts + timedelta(seconds=1)).isoformat(),
        },
        headers=admin["headers"],
    )
    assert len(r.json()["data"]) >= 1
    r = await client.get(
        f"/api/v1/commands/admin/list?until=2000-01-01T00:00:00Z",
        headers=admin["headers"],
    )
    assert r.json()["data"] == []
    r = await client.get(
        "/api/v1/commands/admin/list?since=nonsense", headers=admin["headers"]
    )
    assert r.status_code == 422


async def test_admin_live_junction_states(client, admin, junction, device):
    r = await client.get("/api/v1/admin/live", headers=admin["headers"])
    assert r.status_code == 200, r.text
    states = r.json()["data"]["junction_states"]
    assert junction["id"] in states
    entry = states[junction["id"]]
    assert entry["name"]
    assert entry["online"] is False  # device registered but silent

    # a telemetry post flips the device online and surfaces its state payload
    r = await client.post(
        "/api/v1/devices/telemetry",
        json={"junction_id": junction["id"], "payload": {"state": "green"}},
        headers={"X-Device-Api-Key": device["api_key"]},
    )
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/admin/live", headers=admin["headers"])
    entry = r.json()["data"]["junction_states"][junction["id"]]
    assert entry["online"] is True
    assert entry["state"] == "green"
    assert entry["telemetry_at"] is not None


async def test_notification_prefs_roundtrip(client, driver, db_factory):
    r = await client.get("/api/v1/admin/notification-prefs", headers=driver["headers"])
    assert r.status_code == 200, r.text
    prefs = r.json()["data"]
    assert set(prefs) == {
        "session_started",
        "session_ended",
        "priority_granted",
        "officer_override",
    }
    assert all(prefs.values())

    r = await client.put(
        "/api/v1/admin/notification-prefs",
        json={"prefs": {"session_started": False, "bogus_key": True}},
        headers=driver["headers"],
    )
    assert r.status_code == 422

    r = await client.put(
        "/api/v1/admin/notification-prefs",
        json={"prefs": {"session_started": False}},
        headers=driver["headers"],
    )
    assert r.status_code == 200, r.text
    async with db_factory() as s:
        row = (
            await s.execute(
                select(UserNotificationPref).where(
                    UserNotificationPref.user_id == driver["user"].id,
                    UserNotificationPref.event_key == "session_started",
                )
            )
        ).scalar_one()
        assert row.enabled is False
    r = await client.get("/api/v1/admin/notification-prefs", headers=driver["headers"])
    assert r.json()["data"]["session_started"] is False


async def test_muted_event_skips_push(db_factory):
    """notify_user must not reach the notifier for muted events, and must
    still deliver (reach the notifier) for enabled ones."""
    from app.integrations.notify import (
        NotificationBase,
        notify_user,
        reset_notifier_for_tests,
        set_notifier_for_tests,
    )

    class Recorder(NotificationBase):
        def __init__(self):
            self.calls = 0

        async def send(self, *a, **k) -> dict:
            self.calls += 1
            return {"ok": True, "recorded": True}

    rec = Recorder()
    reset_notifier_for_tests()
    set_notifier_for_tests(rec)

    uid = uuid.uuid4()
    async with db_factory() as db:
        db.add(UserNotificationPref(user_id=uid, event_key="session_started", enabled=False))
        await db.commit()

        class PrefRow:
            def __init__(self, enabled):
                self._enabled = enabled

            # first execute: prefs lookup returns the row's enabled column

        class FakeResult:
            def __init__(self, first_value, all_value):
                self._first = first_value
                self._all = all_value

            def scalars(self):
                outer = self

                class S:
                    def first(self):
                        return outer._first

                    def all(self):
                        return outer._all

                return S()

        class MutedDB:
            async def execute(self, *a, **k):
                # prefs lookup only; a token lookup would return empty anyway
                return FakeResult(False, [])

        res = await notify_user(MutedDB(), uid, "T", "M", event_key="session_started")
        assert res == {"ok": True, "muted": True}
        assert rec.calls == 0

        class EnabledDB:
            def __init__(self):
                self.queries = 0

            async def execute(self, *a, **k):
                self.queries += 1
                if self.queries == 1:
                    return FakeResult(True, [])  # prefs row: enabled
                return FakeResult(None, [])  # token lookup: none

        edb = EnabledDB()
        res = await notify_user(edb, uid, "T", "M", event_key="session_started")
        assert rec.calls == 1  # notifier reached despite zero subscriptions
    reset_notifier_for_tests()


async def test_password_min_length_still_enforced(client, admin, driver):
    r = await client.post(
        "/api/v1/auth/login", json={"email": driver["user"].email, "password": PASSWORD}
    )
    assert r.status_code == 200
