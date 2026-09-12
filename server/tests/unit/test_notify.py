import pytest

from app.integrations.notify import (
    MockOneSignal,
    get_notifier,
    notify_user,
    reset_notifier_for_tests,
)


@pytest.mark.asyncio
async def test_mock_notifier_records():
    reset_notifier_for_tests()
    n = get_notifier()
    assert isinstance(n, MockOneSignal)
    res = await n.send("Hi", "Body", player_ids=["p1"], user_id="u1")
    assert res["ok"] is True
    assert n.sent[-1]["player_ids"] == ["p1"]


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
    assert res["ok"] is True  # mock records with empty player list
