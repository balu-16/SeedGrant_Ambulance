"""Expo Push Service sender (delivery runs over FCM transport on Android).

Single backend abstraction for real device pushes. Messages are POSTed to
https://exp.host/--/api/v2/push/send in chunks of ≤100 with per-ticket status
parsing. All sends are best-effort — failures are logged and returned, never
raised — so notification problems can never break emergency flows.

Secrets: none required. The Firebase Admin JSON stays reserved for a future
direct-FCM path and is never used here.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

log = get_logger("push_sender")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
MAX_CHUNK = 100


def is_expo_token(token: str) -> bool:
    """True for Expo Push Tokens issued to real devices."""
    return token.startswith("ExponentPushToken[") and token.endswith("]")


def build_message(token: str, title: str, body: str) -> dict:
    return {
        "to": token,
        "title": title,
        "body": body,
        "sound": "default",
        "priority": "high",
        "channelId": "default",
    }


async def _send_chunk(messages: list[dict]) -> list[dict]:
    """POST one chunk; returns per-message ticket dicts (test seam)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            EXPO_PUSH_URL,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=messages,
        )
    if resp.status_code >= 300:
        log.error("expo_push_http_failed", status=resp.status_code, body=resp.text[:300])
        return [{"status": "error", "message": f"http {resp.status_code}"} for _ in messages]
    try:
        data = resp.json().get("data", [])
    except Exception:
        return [{"status": "error", "message": "bad receipt body"} for _ in messages]
    return data if isinstance(data, list) else []


async def send_expo_push(tokens: list[str], title: str, body: str) -> dict:
    """Send to Expo Push Tokens only (others are skipped, not failed).

    Returns {"ok", "sent", "skipped", "errors"} — never raises.
    """
    targets = [t for t in tokens if is_expo_token(t)]
    skipped = len(tokens) - len(targets)
    sent, errors = 0, 0
    try:
        messages = [build_message(t, title, body) for t in targets]
        for i in range(0, len(messages), MAX_CHUNK):
            for ticket in await _send_chunk(messages[i : i + MAX_CHUNK]):
                if isinstance(ticket, dict) and ticket.get("status") == "ok":
                    sent += 1
                else:
                    errors += 1
                    log.warning("expo_push_ticket_error", ticket=str(ticket)[:200])
        log.info("expo_push_sent", sent=sent, errors=errors, skipped=skipped)
        return {"ok": errors == 0, "sent": sent, "skipped": skipped, "errors": errors}
    except Exception as e:
        log.error("expo_push_failed", error=str(e))
        return {"ok": False, "sent": sent, "skipped": skipped, "errors": errors, "error": str(e)}
