"""Expo Push sender tests — token filter, chunking, ticket parsing."""

import pytest

from app.services import push_sender
from app.services.push_sender import build_message, is_expo_token, send_expo_push

REAL = "ExponentPushToken[abc123]"
OTHER = "onesignal-player-id"


def test_is_expo_token():
    assert is_expo_token(REAL) is True
    assert is_expo_token(OTHER) is False
    assert is_expo_token("") is False
    assert is_expo_token("ExponentPushToken[abc") is False


def test_build_message_shape():
    m = build_message(REAL, "T", "B")
    assert m["to"] == REAL
    assert m["title"] == "T" and m["body"] == "B"
    assert m["channelId"] == "default"


@pytest.mark.asyncio
async def test_non_expo_tokens_skipped_without_http(monkeypatch):
    async def fail_chunk(_):
        raise AssertionError("no HTTP for non-expo tokens")

    monkeypatch.setattr(push_sender, "_send_chunk", fail_chunk)
    res = await send_expo_push([OTHER, ""], "T", "B")
    assert res == {"ok": True, "sent": 0, "skipped": 2, "errors": 0}


@pytest.mark.asyncio
async def test_ticket_parsing_and_chunking(monkeypatch):
    seen: list = []

    async def fake_chunk(messages):
        seen.append(len(messages))
        return [{"status": "ok"} for _ in messages] + [
            {"status": "error", "message": "DeviceNotRegistered"}
        ]

    monkeypatch.setattr(push_sender, "_send_chunk", fake_chunk)
    tokens = [f"ExponentPushToken[{i}]" for i in range(3)]
    res = await send_expo_push(tokens, "T", "B")
    assert seen == [3]
    assert res["sent"] == 3 and res["errors"] == 1 and res["skipped"] == 0
    assert res["ok"] is False


@pytest.mark.asyncio
async def test_sender_never_raises(monkeypatch):
    async def boom(_):
        raise RuntimeError("net down")

    monkeypatch.setattr(push_sender, "_send_chunk", boom)
    res = await send_expo_push([REAL], "T", "B")
    assert res["ok"] is False and "error" in res
