import pytest

from app.integrations.notify import (
    LogNotifier,
    NotificationBase,
    get_notifier,
    notify_user,
    reset_notifier_for_tests,
    set_notifier_for_tests,
)


class RecordingNotifier(NotificationBase):
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, title, message, player_ids=None, user_id=None) -> dict:
        self.sent.append(
            {
                "title": title,
                "message": message,
                "player_ids": list(player_ids or []),
                "user_id": user_id,
            }
        )
        return {"ok": True, "recorded": True}


@pytest.mark.asyncio
async def test_default_notifier_is_log_only():
    reset_notifier_for_tests()
    assert isinstance(get_notifier(), LogNotifier)
    res = await get_notifier().send("Hi", "Body", player_ids=["p1"], user_id="u1")
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_injected_notifier_records():
    reset_notifier_for_tests()
    rec = RecordingNotifier()
    set_notifier_for_tests(rec)
    res = await get_notifier().send("Hi", "Body", player_ids=["p1"], user_id="u1")
    assert res["ok"] is True
    assert rec.sent[-1]["player_ids"] == ["p1"]
    reset_notifier_for_tests()
    assert isinstance(get_notifier(), LogNotifier)


@pytest.mark.asyncio
async def test_notify_user_never_raises_without_devices():
    reset_notifier_for_tests()

    class FakeResult:
        def scalars(self):
            class S:
                def all(self):
                    return []

            return S()

    class FakeDB:
        async def execute(self, *a, **k):
            return FakeResult()

    res = await notify_user(FakeDB(), "some-user", "T", "M")
    assert res["ok"] is True  # log-only path with empty player list
