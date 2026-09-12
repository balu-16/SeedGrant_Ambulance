"""Push notifications (mock notifier; delivery via Expo Push Service).

Mobile flow (React Native, not yet built):
  1. POST /api/v1/auth/login  → tokens
  2. App asks OS notification permission via expo-notifications
  3. POST /api/v1/push/register {player_id}  (driver JWT)
Backend stores (user_id, player_id) and targets player_ids on events.
"""

from abc import ABC, abstractmethod

from app.core.logging import get_logger

log = get_logger("notify")


class NotificationBase(ABC):
    @abstractmethod
    async def send(
        self,
        title: str,
        message: str,
        player_ids: list[str] | None = None,
        user_id: str | None = None,
    ) -> dict: ...


class MockOneSignal(NotificationBase):
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, title, message, player_ids=None, user_id=None) -> dict:
        rec = {
            "title": title,
            "message": message,
            "player_ids": player_ids or [],
            "user_id": user_id,
        }
        self.sent.append(rec)
        log.info("mock_notify_send", **{k: str(v) for k, v in rec.items()})
        return {"ok": True, "mock": True}


_singletons: dict[str, NotificationBase] = {}


def get_notifier() -> NotificationBase:
    """Factory — always returns the mock notifier (real delivery = Expo Push)."""
    if "mock" not in _singletons:
        _singletons["mock"] = MockOneSignal()
    return _singletons["mock"]


def reset_notifier_for_tests() -> None:
    _singletons.clear()


async def notify_user(db, user_id, title: str, message: str) -> dict:
    """Best-effort push to all of a user's subscribed devices. Never raises."""
    try:
        from sqlalchemy import select

        from app.models.device import PushSubscription

        rows = (
            (await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id)))
            .scalars()
            .all()
        )
        player_ids = [r.player_id for r in rows]
        result = await get_notifier().send(
            title, message, player_ids=player_ids, user_id=str(user_id)
        )
        # Real device delivery via Expo Push Service (FCM transport on Android).
        # Best-effort: only ExponentPushToken ids are sent; never raises.
        try:
            from app.services.push_sender import is_expo_token, send_expo_push

            expo_ids = [p for p in player_ids if is_expo_token(p)]
            if expo_ids:
                expo_result = await send_expo_push(expo_ids, title, message)
                result = {**result, "expo": expo_result}
        except Exception as e:
            log.warning("expo_push_skipped", error=str(e))
        log.info("notify_user", user_id=str(user_id), title=title, result=str(result)[:200])
        return result
    except Exception as e:
        log.error("notify_user_failed", user_id=str(user_id), error=str(e))
        return {"ok": False, "error": str(e)}
