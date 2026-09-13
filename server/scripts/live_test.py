"""Live end-to-end test against REAL services (Supabase, EMQX, best.pt).

Run where the database is reachable (NOT in an offline sandbox):
    cd server && source .venv/bin/activate
    alembic upgrade head && python -m app.db.seed
    python main.py &  # or: python main.py --reload
    python scripts/live_test.py --base http://localhost:8000 [--gap 3]

Flow: health → admin login → create Mumbai test junction → driver login →
my ambulance → start emergency → stream 12 GPS fixes into the geofence →
assert priority requested + command issued → device pending/ack →
stop → history → profile round-trip → detection ingest/list →
push register/list/delete →
logout + revoked-refresh check. Each step prints PASS/FAIL/SKIP;
exit code is 1 when any step fails.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

ADMIN_EMAIL = "admin@demo.io"
ADMIN_PASS = "Admin123!"
DRIVER_EMAIL = "driver@demo.io"
DRIVER_PASS = "Demo123!"

# Mumbai test junction (route[0] area from the driver app).
JUNCTION = {"name": "E2E Bandra Test", "latitude": 19.0596, "longitude": 72.8295}
# Walk-in: start ~1.6km east, end at the junction (heading west, ~8 m/s).
FIXES = 12
LON_START, LON_END = 72.8450, 72.8295
LAT = 19.0596

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, "PASS" if ok else "FAIL", detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def req(client: httpx.Client, method: str, path: str, token: str | None = None, **kw):
    headers = dict(kw.pop("headers", {}))
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = client.request(method, path, headers=headers, timeout=20.0, **kw)
    except httpx.HTTPError as e:
        print(f"[FAIL] {method} {path} — unreachable: {e.__class__.__name__}")
        return 0, {}
    try:
        body = r.json()
    except Exception:
        body = {}
    return r.status_code, body


def main() -> int:
    ap = argparse.ArgumentParser(description="Live E2E against real backend services.")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--gap", type=float, default=3.0, help="seconds between GPS fixes")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    c = httpx.Client(base_url=base)

    # 0. Health.
    code, body = req(c, "GET", "/health")
    if not check("health", code == 200 and body.get("success") is True, f"http {code}"):
        return 1

    # 1. Admin login.
    code, body = req(
        c, "POST", "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
    )
    if not check("admin login", code == 200, f"http {code}"):
        return 1
    admin_tok = body["data"]["access_token"]

    # 2. Mumbai test junction (auto-creates 4 approaches).
    code, body = req(
        c, "POST", "/api/v1/junctions",
        token=admin_tok,
        json={**JUNCTION, "radius_m": 500.0},
    )
    if not check("create junction", code in (200, 201), f"http {code}"):
        return 1
    jid = body["data"]["id"]

    # 3. Driver login.
    code, body = req(
        c, "POST", "/api/v1/auth/login",
        json={"email": DRIVER_EMAIL, "password": DRIVER_PASS},
    )
    if not check("driver login", code == 200, f"http {code}"):
        return 1
    driver_tok = body["data"]["access_token"]
    driver_refresh = body["data"]["refresh_token"]

    # 4. Assigned ambulance.
    code, body = req(c, "GET", "/api/v1/ambulances/mine", token=driver_tok)
    if not check("my ambulance", code == 200, f"http {code}"):
        return 1
    aid = body["data"]["id"]
    print(f"      ambulance {body['data']['vehicle_no']} ({aid})")

    # 5. Start emergency.
    code, body = req(
        c, "POST", "/api/v1/emergencies/start", token=driver_tok,
        json={"ambulance_id": aid},
    )
    if not check("start emergency", code == 200, f"http {code}"):
        return 1
    sid = body["data"]["session_id"]

    # 6. Real GPS fix stream into the geofence.
    saw_priority = False
    saw_command: dict | None = None
    for i in range(FIXES):
        lon = LON_START + (LON_END - LON_START) * i / (FIXES - 1)
        code, body = req(
            c, "POST", f"/api/v1/emergencies/{sid}/gps", token=driver_tok,
            json={
                "latitude": LAT,
                "longitude": round(lon, 6),
                "accuracy": 8.0,
                "speed": 8.0,
                "heading": 270.0,
            },
        )
        if code != 200:
            check(f"gps fix {i + 1}", False, f"http {code} {body}")
            return 1
        st = body["data"].get("status")
        cmd = body["data"].get("command")
        print(f"      fix {i + 1}/{FIXES} status={st} command={bool(cmd)}")
        if st in ("APPROACHING_JUNCTION", "PRIORITY_REQUESTED", "CROSSING"):
            saw_priority = True
        if cmd:
            saw_command = cmd
        time.sleep(args.gap)
    check("gps stream accepted", True, f"{FIXES} fixes")
    check("priority triggered", saw_priority, "geofence entered")
    check("command issued", saw_command is not None, str((saw_command or {}).get("type")))

    # 7. Device pending/ack for the test junction.
    code, body = req(
        c, "POST", "/api/v1/admin/devices/register", token=admin_tok,
        params={"junction_id": jid, "name": "E2E-PI"},
    )
    if not check("register device", code == 200, f"http {code}"):
        return 1
    dev_key = body["data"]["api_key"]
    code, body = req(
        c, "GET", "/api/v1/commands/pending", headers={"X-Device-Api-Key": dev_key},
        params={"junction_id": jid},
    )
    pending = body.get("data", []) if code == 200 else []
    check("pending commands", code == 200 and len(pending) > 0, f"{len(pending)} pending")
    if pending:
        cid = pending[0]["id"]
        code, _ = req(
            c, "POST", f"/api/v1/commands/{cid}/ack",
            headers={"X-Device-Api-Key": dev_key},
        )
        check("ack command", code == 200, f"http {code}")

    # 8. Stop + history.
    code, body = req(c, "POST", f"/api/v1/emergencies/{sid}/stop", token=driver_tok)
    check("stop emergency", code == 200, f"http {code}")
    code, body = req(c, "GET", "/api/v1/emergencies/history", token=driver_tok)
    ids = [s["id"] for s in body.get("data", [])] if code == 200 else []
    check("history shows session", sid in ids, f"{len(ids)} sessions")

    # 8b. Driver profile round-trip (driver_profiles table).
    code, body = req(c, "GET", "/api/v1/auth/profile", token=driver_tok)
    check("get profile", code == 200 and "hospital" in body.get("data", {}),
          f"http {code}")
    code, body = req(
        c, "PATCH", "/api/v1/auth/profile", token=driver_tok,
        json={"hospital": "Bhabha Hospital, Bandra", "region": "Bandra West, Mumbai"},
    )
    check("patch profile", code == 200 and body.get("data", {}).get("hospital")
          == "Bhabha Hospital, Bandra", f"http {code}")

    # 8c. Detection ingest + list (detections table).
    code, body = req(
        c, "POST", "/api/v1/vision/detections", token=driver_tok,
        json=[{
            "session_id": sid,
            "junction_id": jid,
            "vehicle_class": "car",
            "class_name": "Sedan",
            "confidence": 0.88,
            "bbox": {"x1": 10, "y1": 20, "x2": 100, "y2": 120},
        }],
    )
    check("ingest detection", code == 200 and body.get("data", {}).get("stored") == 1,
          f"http {code}")
    # detections listing is ADMIN-only (cross-junction rows)
    code, body = req(
        c, "GET", "/api/v1/vision/detections", token=admin_tok,
        params={"junction_id": jid, "limit": 5},
    )
    rows = body.get("data", []) if code == 200 else []
    check("list detections", code == 200 and any(
        r["class_name"] == "Sedan" for r in rows), f"{len(rows)} rows")

    # 9. Push register/list/delete (fake Expo token: exercises the path;
    # real delivery needs a device token).
    fake = "ExponentPushToken[e2e-test-token]"
    code, body = req(
        c, "POST", "/api/v1/push/register", token=driver_tok,
        json={"player_id": fake, "expo_push_token": fake, "device_type": "android"},
    )
    check("push register", code == 200, f"http {code}")
    code, body = req(c, "GET", "/api/v1/push", token=driver_tok)
    check("push list", code == 200 and any(
        r["player_id"] == fake for r in body.get("data", [])), f"http {code}")
    code, _ = req(c, "DELETE", f"/api/v1/push/{fake}", token=driver_tok)
    check("push delete", code == 200, f"http {code}")

    # 11. Logout revokes refresh.
    code, _ = req(c, "POST", "/api/v1/auth/logout", token=driver_tok)
    check("logout", code == 200, f"http {code}")
    code, _ = req(c, "POST", "/api/v1/auth/refresh",
                  json={"refresh_token": driver_refresh})
    check("refresh revoked", code == 401, f"http {code}")

    print(f"\nJunction left behind for inspection: {JUNCTION['name']} ({jid})")
    failed = [n for n, s, _ in results if s == "FAIL"]
    print(f"RESULT: {len(results) - len(failed)}/{len(results)} ok"
          + (f" — FAILED: {failed}" if failed else " — ALL GREEN"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
