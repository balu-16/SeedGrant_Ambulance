"""SeedGrant demo simulator: isolated demo seeding + scripted emergency journey.

Modes:
    python -m scripts.simulator --seed-only     # seed demo data and exit
    python -m scripts.simulator [--base URL]    # seed (idempotent) + full journey

Gating (contract §7): before ANY seeding or sending the simulator re-validates
from its own environment that it is running against the isolated demo
configuration — DEMO_MODE=1, ENVIRONMENT=dev, MQTT_PROVIDER=mock, and database
URLs pointing at a LOCAL database whose name contains "demo". Any mismatch
hard-fails with a clear message. The notifier must stay LogNotifier (demo never
calls push services).

Journey (contract §8, PASS/FAIL steps like scripts/live_test.py):
driver login → start emergency → 12 GPS fixes → PRIORITY_REQUEST → device
poll + ack (with attempt) → POLICE HOLD → release pending → device acks
release → REISSUE → ack → FORCE_RELEASE → ack → second emergency left to
expire (COMMAND_TTL) → session timeout → device offline → admin/hospital/
police scoped API spot-checks (live totals, alerts, export.csv).
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

# ---- demo constants (contract §8) -------------------------------------------

ADMIN_EMAIL, ADMIN_PASS = "admin@demo.io", "Admin123!"
HOSPITAL_EMAIL, HOSPITAL_PASS = "hospital@demo.io", "Hospital123!"
POLICE_EMAIL, POLICE_PASS = "police@demo.io", "Police123!"
DRIVER_EMAIL, DRIVER_PASS = "driver@demo.io", "Demo123!"

HOSPITAL_NAME = "Demo General Hospital"
JUNCTION_NAME = "Demo Junction"
JUNCTION_LAT, JUNCTION_LON = 16.5062, 80.6480  # Vijayawada
JUNCTION_RADIUS_M = 400
AMBULANCE_VEHICLE = "DEMO-101"
DEVICE_NAME = "PI-DEMO-01"

# Walk-in: start ~1.7km east of the junction, drive west into the geofence
# (heading 270° = WEST approach window). The walk STOPS ~107m east of the
# junction center — inside the 400m geofence so the approach fires, but
# outside the ~75m has_crossed trigger zone so the priority is NOT released
# mid-journey (the crossing/release path is exercised via HOLD/FORCE_RELEASE).
FIXES = 12
LON_START, LON_END = JUNCTION_LON + 0.0160, JUNCTION_LON + 0.0010
LAT = JUNCTION_LAT

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, "PASS" if ok else "FAIL", detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def skip(name: str, reason: str) -> None:
    results.append((name, "SKIP", reason))
    print(f"[SKIP] {name} — {reason}")


# ---- gating (contract §7) ----------------------------------------------------


def check_demo_gates(settings=None) -> list[str]:
    """Re-validate the demo conditions from the process environment.

    Importable + network-free so tests can call it directly. Returns a list of
    human-readable failures; an empty list means the demo gates are satisfied.
    """
    import os

    failures: list[str] = []
    demo_env = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")
    if not demo_env:
        failures.append("DEMO_MODE=1 must be set in the process environment")

    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    if settings.ENVIRONMENT.lower() not in ("dev", "development"):
        failures.append(f"ENVIRONMENT must be dev (got {settings.ENVIRONMENT!r})")
    if settings.mqtt_is_real:
        failures.append("MQTT_PROVIDER must be mock in demo mode (never dial a real broker)")
    for name in ("DATABASE_URL", "SYNC_DATABASE_URL"):
        url = getattr(settings, name, "")
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        dbname = (parts.path or "").lstrip("/")
        if host not in ("localhost", "127.0.0.1", "::1"):
            failures.append(f"{name} must point at localhost/127.0.0.1 (got host {host!r})")
        elif "demo" not in dbname.lower():
            failures.append(f"{name} must target a *demo* database (got {dbname!r})")
    # the demo must never be able to call push services
    from app.integrations.notify import LogNotifier, get_notifier

    if not isinstance(get_notifier(), LogNotifier):
        failures.append("notifier must stay LogNotifier in demo mode (no push services)")
    return failures


# ---- seeding (idempotent upserts, direct DB like app.db.seed) ----------------


async def seed_demo() -> str:
    """Upsert the demo dataset; returns the (fresh) device API key."""
    import secrets

    from sqlalchemy import select

    import app.models  # noqa: F401
    from app.core.dependencies import hash_api_key
    from app.core.security import hash_password
    from app.db.session import get_session_factory
    from app.models.device import Device
    from app.models.hospital import Hospital
    from app.models.junction import Approach, Junction, PoliceAssignment
    from app.models.user import Ambulance, User
    from app.utils.geo import offset_point

    factory = get_session_factory()
    async with factory() as db:
        hospital = (
            await db.execute(select(Hospital).where(Hospital.name == HOSPITAL_NAME))
        ).scalar_one_or_none()
        if hospital is None:
            hospital = Hospital(
                name=HOSPITAL_NAME,
                address="MG Road, Vijayawada (demo)",
                latitude=JUNCTION_LAT,
                longitude=JUNCTION_LON,
                phone="+918661234567",
            )
            db.add(hospital)
            await db.flush()

        async def _upsert_user(email: str, password: str, role: str) -> User:
            u = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if u is None:
                u = User(email=email, password_hash=hash_password(password), role=role)
                db.add(u)
            else:
                u.password_hash = hash_password(password)
                u.role = role
                u.is_active = True
            u.hospital_id = hospital.id if role == "hospital" else u.hospital_id
            await db.flush()
            return u

        await _upsert_user(ADMIN_EMAIL, ADMIN_PASS, "admin")
        await _upsert_user(HOSPITAL_EMAIL, HOSPITAL_PASS, "hospital")
        police = await _upsert_user(POLICE_EMAIL, POLICE_PASS, "police")
        driver = await _upsert_user(DRIVER_EMAIL, DRIVER_PASS, "driver")

        j = (
            await db.execute(select(Junction).where(Junction.name == JUNCTION_NAME))
        ).scalar_one_or_none()
        if j is None:
            j = Junction(
                name=JUNCTION_NAME,
                latitude=JUNCTION_LAT,
                longitude=JUNCTION_LON,
                radius_m=JUNCTION_RADIUS_M,
            )
            db.add(j)
            await db.flush()
            windows = {
                "NORTH": (300, 60), "SOUTH": (120, 240),
                "EAST": (30, 150), "WEST": (210, 330),
            }
            entries = {
                "NORTH": (0, 150), "SOUTH": (180, 150),
                "EAST": (90, 150), "WEST": (270, 150),
            }
            for d, (lo, hi) in windows.items():
                b, dist = entries[d]
                elat, elon = offset_point(JUNCTION_LAT, JUNCTION_LON, b, dist)
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
            await db.flush()
        pa = (
            await db.execute(
                select(PoliceAssignment).where(
                    PoliceAssignment.user_id == police.id,
                    PoliceAssignment.junction_id == j.id,
                )
            )
        ).scalar_one_or_none()
        if pa is None:
            db.add(PoliceAssignment(user_id=police.id, junction_id=j.id))

        amb = (
            await db.execute(select(Ambulance).where(Ambulance.vehicle_no == AMBULANCE_VEHICLE))
        ).scalar_one_or_none()
        if amb is None:
            amb = Ambulance(
                vehicle_no=AMBULANCE_VEHICLE, driver_id=driver.id, hospital_id=hospital.id
            )
            db.add(amb)
        else:
            amb.driver_id = driver.id
            amb.hospital_id = hospital.id

        dev = (
            await db.execute(select(Device).where(Device.junction_id == j.id))
        ).scalar_one_or_none()
        raw = secrets.token_hex(24)
        if dev is None:
            dev = Device(junction_id=j.id, name=DEVICE_NAME, api_key_hash=hash_api_key(raw))
            db.add(dev)
        else:
            # the hash is one-way: rotate so the printed key always works
            dev.name = DEVICE_NAME
            dev.api_key_hash = hash_api_key(raw)
            dev.is_online = False
        await db.commit()
        print(f"[seed] hospital={hospital.name} junction={j.id} "
              f"ambulance={amb.vehicle_no} users=4")
        print(f"DEVICE_API_KEY (shown once)={raw}")
        return raw


# ---- journey -----------------------------------------------------------------


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    r = await client.post("/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise RuntimeError(f"login failed for {email}: HTTP {r.status_code} {r.text[:200]}")
    return r.json()["data"]["access_token"]


async def _req(client, method, path, token=None, **kw):
    headers = dict(kw.pop("headers", {}))
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = await client.request(method, path, headers=headers, **kw)
    try:
        body = r.json()
    except Exception:
        body = {}
    return r.status_code, body


async def journey(base: str, dev_key: str, gap: float, skip_long_waits: bool) -> int:
    async with httpx.AsyncClient(base_url=base, timeout=30.0) as c:
        admin_tok = await _login(c, ADMIN_EMAIL, ADMIN_PASS)
        hospital_tok = await _login(c, HOSPITAL_EMAIL, HOSPITAL_PASS)
        police_tok = await _login(c, POLICE_EMAIL, POLICE_PASS)
        driver_tok = await _login(c, DRIVER_EMAIL, DRIVER_PASS)
        check("demo logins (admin/hospital/police/driver)", True)

        # junction id via the demo device key's junction — resolve through the
        # junctions list (name lookup is deterministic after seeding)
        code, body = await _req(c, "GET", "/junctions", admin_tok, params={"limit": 500})
        jid = None
        for row in body.get("data", []) if code == 200 else []:
            if row.get("name") == JUNCTION_NAME:
                jid = row["id"]
        if not check("demo junction present", jid is not None, str(jid)):
            return _summary()

        # 1. driver → ambulance → start emergency
        code, body = await _req(c, "GET", "/ambulances/mine", driver_tok)
        aid = body.get("data", {}).get("id") if code == 200 else None
        if not check("driver ambulance (DEMO-101)", aid is not None, str(aid)):
            return _summary()
        # A previous aborted journey may have left an ACTIVE session on this
        # ambulance (one-active-session guard) — stop it so re-runs work.
        code, body = await _req(c, "GET", "/emergencies/current", driver_tok)
        stale = body.get("data", {}) if code == 200 else {}
        if code == 200 and stale.get("session_id"):
            await _req(c, "POST", f"/emergencies/{stale['session_id']}/stop", driver_tok)
        code, body = await _req(
            c, "POST", "/emergencies/start", driver_tok,
            json={"ambulance_id": aid, "hospital": HOSPITAL_NAME},
        )
        sid = body.get("data", {}).get("session_id") if code == 200 else None
        if not check("start emergency", code == 200 and sid is not None, f"http {code}"):
            return _summary()

        # 2. GPS walk-in → expect PRIORITY_REQUEST
        saw_command = None
        for i in range(FIXES):
            lon = LON_START + (LON_END - LON_START) * i / (FIXES - 1)
            code, body = await _req(
                c, "POST", f"/emergencies/{sid}/gps", driver_tok,
                json={"latitude": LAT, "longitude": round(lon, 6), "accuracy": 8.0,
                      "speed": 8.0, "heading": 270.0},
            )
            if code != 200:
                check(f"gps fix {i + 1}", False, f"http {code} {str(body)[:150]}")
                break
            cmd = body["data"].get("command")
            if cmd and cmd.get("type") == "PRIORITY_REQUEST":
                saw_command = cmd
            await asyncio.sleep(gap)
        else:
            check("12 GPS fixes accepted", True)
        if not check("PRIORITY_REQUEST issued", saw_command is not None,
                     str((saw_command or {}).get("type"))):
            return _summary()

        # 3. device poll + ack (with attempt)
        code, body = await _req(
            c, "GET", "/commands/pending", None,
            headers={"X-Device-Api-Key": dev_key}, params={"junction_id": jid},
        )
        pending = body.get("data", []) if code == 200 else []
        priority = next((p for p in pending if p["id"] == saw_command["id"]), None)
        if not check("device poll sees the priority (attempt in envelope)",
                     priority is not None and "attempt" in (priority or {}),
                     f"{len(pending)} pending"):
            return _summary()
        code, body = await _req(
            c, "POST", f"/commands/{priority['id']}/ack", None,
            headers={"X-Device-Api-Key": dev_key},
            json={"attempt": priority.get("attempt", 1)},
        )
        check(
            "device acks priority with attempt",
            code == 200 and body.get("data", {}).get("acked") is True,
            f"http {code}",
        )

        # 4. POLICE HOLD → release published (device had the command: SENT/ACKED)
        code, body = await _req(
            c, "POST", f"/junctions/{jid}/override", police_tok,
            json={"action": "HOLD", "reason": "simulator hold: pedestrian crossing"},
        )
        release = body.get("data", {}).get("release") if code == 200 else None
        check("police HOLD publishes a release (device had received the request)",
              code == 200 and release is not None
              and (body.get("data", {}).get("delivery") or {}).get("status") == "PENDING",
              f"http {code} release={bool(release)}")

        # 5. device acks the release
        code, body = await _req(
            c, "GET", "/commands/pending", None,
            headers={"X-Device-Api-Key": dev_key}, params={"junction_id": jid},
        )
        pending = body.get("data", []) if code == 200 else []
        rel = next((p for p in pending if p.get("type") == "RELEASE_PRIORITY"), None)
        check("release pending for device", rel is not None, f"{len(pending)} pending")
        if rel is not None:
            code, _ = await _req(
                c, "POST", f"/commands/{rel['id']}/ack", None,
                headers={"X-Device-Api-Key": dev_key}, json={"attempt": rel.get("attempt", 1)},
            )
            check("device acks release", code == 200, f"http {code}")

        # 6. REISSUE (release acked, session active) → ack attempt 2
        code, body = await _req(
            c, "POST", f"/junctions/{jid}/override", police_tok,
            json={"action": "REISSUE", "reason": "simulator reissue: corridor clear"},
        )
        reissued = body.get("data", {}).get("command") if code == 200 else None
        check("police REISSUE issues attempt 2",
              code == 200 and reissued is not None and reissued.get("attempt") == 2,
              f"http {code}")
        if reissued is not None:
            code, _ = await _req(
                c, "POST", f"/commands/{reissued['id']}/ack", None,
                headers={"X-Device-Api-Key": dev_key}, json={"attempt": reissued["attempt"]},
            )
            check("device acks reissue", code == 200, f"http {code}")

        # 7. FORCE_RELEASE → ack
        code, body = await _req(
            c, "POST", f"/junctions/{jid}/override", police_tok,
            json={"action": "FORCE_RELEASE", "reason": "simulator force release"},
        )
        frel = body.get("data", {}).get("release") if code == 200 else None
        check(
            "police FORCE_RELEASE publishes release",
            code == 200 and frel is not None,
            f"http {code}",
        )
        if frel is not None:
            code, _ = await _req(
                c, "POST", f"/commands/{frel['id']}/ack", None,
                headers={"X-Device-Api-Key": dev_key}, json={"attempt": frel.get("attempt", 1)},
            )
            check("device acks force release", code == 200, f"http {code}")

        # 8. stop session 1, start session 2 and let it expire (COMMAND_TTL)
        code, _ = await _req(c, "POST", f"/emergencies/{sid}/stop", driver_tok)
        check("stop first emergency", code == 200, f"http {code}")
        code, body = await _req(
            c, "POST", "/emergencies/start", driver_tok,
            json={"ambulance_id": aid, "hospital": HOSPITAL_NAME},
        )
        sid2 = body.get("data", {}).get("session_id") if code == 200 else None
        if not check("start second emergency (timeout scenario)", code == 200 and sid2 is not None,
                     f"http {code}"):
            return _summary()
        # Short walk-in (same geometry rules as the first: end ~107m east,
        # no crossing) so the approach is detected and a priority is issued.
        cmd2 = None
        for i in range(4):
            lon = JUNCTION_LON + 0.0040 + (LON_END - (JUNCTION_LON + 0.0040)) * i / 3
            code, body = await _req(
                c, "POST", f"/emergencies/{sid2}/gps", driver_tok,
                json={"latitude": LAT, "longitude": round(lon, 6), "accuracy": 8.0,
                      "speed": 8.0, "heading": 270.0},
            )
            if code != 200:
                check(f"second emergency gps fix {i + 1}", False, f"http {code}")
                break
            c2 = (body.get("data", {}) or {}).get("command")
            if c2 and c2.get("type") == "PRIORITY_REQUEST":
                cmd2 = c2
            await asyncio.sleep(gap)
        check("second emergency issues a priority", cmd2 is not None)

        from app.core.config import get_settings

        cfg = get_settings()
        ttl_s = cfg.COMMAND_TTL_SECONDS + 20  # TTL + sweeper interval margin
        print(f"      waiting ~{ttl_s}s for COMMAND_TTL expiry ...")
        expired = False
        deadline = time.monotonic() + ttl_s + 30
        while time.monotonic() < deadline:
            code, body = await _req(
                c, "GET", "/commands/admin/list", admin_tok,
                params={"junction_id": jid, "status": "EXPIRED", "limit": 200},
            )
            rows = body.get("data", []) if code == 200 else []
            if cmd2 is not None and any(r["id"] == cmd2["id"] for r in rows):
                expired = True
                break
            await asyncio.sleep(3)
        check("command expired after TTL without ack", expired, f"waited ≤{ttl_s + 30}s")

        # 9. session inactivity timeout (INACTIVITY_TIMEOUT_MINUTES default 5)
        inactivity_s = cfg.INACTIVITY_TIMEOUT_MINUTES * 60 + 30
        if skip_long_waits:
            skip("session times out from inactivity",
                 f"--skip-long-waits (would wait ~{inactivity_s}s)")
        else:
            print(f"      waiting ~{inactivity_s}s for inactivity timeout ...")
            timed_out = False
            deadline = time.monotonic() + inactivity_s + 60
            while time.monotonic() < deadline:
                code, body = await _req(c, "GET", "/emergencies/current", driver_tok)
                data = body.get("data", {}) if code == 200 else {}
                if data.get("session_id") == sid2 and data.get("status") == "TIMED_OUT":
                    timed_out = True
                    break
                await asyncio.sleep(5)
            check("session timed out from inactivity", timed_out, f"waited ≤{inactivity_s + 60}s")

        # 10. device offline (no heartbeat since the last ack)
        offline_s = cfg.DEVICE_OFFLINE_AFTER_SECONDS + 15
        if skip_long_waits:
            skip("device goes offline without heartbeats",
                 f"--skip-long-waits (would wait ~{offline_s}s)")
        else:
            offline = False
            deadline = time.monotonic() + offline_s + 60
            while time.monotonic() < deadline:
                code, body = await _req(c, "GET", "/admin/live", admin_tok)
                st = (body.get("data", {}).get("junction_states") or {}).get(jid, {})
                if st.get("online") is False:
                    offline = True
                    break
                await asyncio.sleep(5)
            check("device offline after DEVICE_OFFLINE_AFTER_SECONDS", offline,
                  f"waited ≤{offline_s + 60}s")

        # 11. scoped API spot-checks
        code, body = await _req(c, "GET", "/admin/live", admin_tok)
        data = body.get("data", {}) if code == 200 else {}
        check("admin live exposes total/cap/observed_at",
              code == 200 and "total" in data and data.get("cap") == 100
              and "observed_at" in data,
              f"http {code} total={data.get('total')}")
        check("admin live items carry owner_hospital_id",
              all("owner_hospital_id" in it for it in data.get("items", [])),
              f"{len(data.get('items', []))} items")

        code, body = await _req(c, "GET", "/admin/live", hospital_tok)
        hdata = body.get("data", {}) if code == 200 else {}
        check("hospital live is ownership-scoped",
              code == 200
              and all(it.get("owner_hospital_id") is not None for it in hdata.get("items", []))
              and hdata.get("junction_states") == {},
              f"{len(hdata.get('items', []))} items")
        code, body = await _req(c, "GET", "/admin/emergencies", hospital_tok)
        rows = body.get("data", {}).get("items", []) if code == 200 else []
        check("hospital history rows show Demo General Hospital ownership",
              code == 200 and len(rows) > 0
              and all(r.get("owner_hospital_name") == HOSPITAL_NAME for r in rows),
              f"{len(rows)} rows")

        code, body = await _req(c, "GET", "/admin/alerts", police_tok)
        check("police alerts feed reachable", code == 200, f"http {code}")

        code, body = await _req(c, "GET", "/portal/status", admin_tok)
        check("portal/status reports simulation=true",
              code == 200 and body.get("data", {}).get("simulation") is True
              and body.get("data", {}).get("manual_controls") is True,
              f"http {code}")

        r = await c.get(
            "/admin/emergencies/export.csv",
            headers={"Authorization": f"Bearer {admin_tok}"},
        )
        header_ok = r.status_code == 200 and r.text.splitlines()[:1] == [
            "emergency_id,status,started_at,ended_at,ended_reason,ambulance,"
            "driver_email,hospital,junctions,duration_minutes"
        ]
        check("export.csv streams the contract header",
              header_ok and "text/csv" in r.headers.get("content-type", ""),
              f"http {r.status_code}")
        return _summary()


def _summary() -> int:
    failed = [n for n, s, _ in results if s == "FAIL"]
    print(
        f"\nRESULT: {len(results) - len(failed)}/{len(results)} ok"
        + (f" — FAILED: {failed}" if failed else " — ALL GREEN")
    )
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SeedGrant demo simulator (gated).")
    ap.add_argument("--base", default="http://localhost:8000/api/v1")
    ap.add_argument("--gap", type=float, default=0.5, help="seconds between GPS fixes")
    ap.add_argument("--seed-only", action="store_true", help="seed demo data and exit")
    ap.add_argument("--skip-long-waits", action="store_true",
                    help="skip the multi-minute inactivity/offline waits (SKIP, not FAIL)")
    args = ap.parse_args()

    failures = check_demo_gates()
    if failures:
        print("DEMO GATE FAILURE — refusing to seed or send anything:")
        for f in failures:
            print(f"  - {f}")
        print("Start the demo backend with server/scripts/run_demo.sh "
              "(DEMO_MODE=1, dev, mock MQTT, localhost *demo* database).")
        return 2

    dev_key = asyncio.run(seed_demo())
    if args.seed_only:
        print("[seed-only] done")
        return 0
    return asyncio.run(journey(args.base.rstrip("/"), dev_key, args.gap, args.skip_long_waits))


if __name__ == "__main__":
    raise SystemExit(main())
