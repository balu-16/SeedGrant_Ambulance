"""Push notifications (Expo Push Service delivery; log-only fallback).

Mobile flow (Expo driver app):
  1. POST /api/v1/auth/login  → tokens
  2. App asks OS notification permission via expo-notifications
  3. POST /api/v1/push/register {player_id}  (driver JWT)
Backend stores (user_id, player_id) and targets player_ids on events.

Real device delivery runs through send_expo_push for ExponentPushToken ids.
Any other player_id format cannot be delivered and is logged and skipped —
there is deliberately no in-process mock in the production path. Tests can
inject a recorder via set_notifier_for_tests().
"""

import asyncio
from abc import ABC, abstractmethod

from app.core.consts import NOTIFICATION_EVENT_KEYS  # noqa: F401 (re-exported)
from app.core.logging import get_logger

log = get_logger("notify")

# keep strong references to fire-and-forget push tasks so GC cannot cancel
# them mid-send
_background_tasks: set[asyncio.Task] = set()


class NotificationBase(ABC):
    @abstractmethod
    async def send(
        self,
        title: str,
        message: str,
        player_ids: list[str] | None = None,
        user_id: str | None = None,
    ) -> dict: ...


class LogNotifier(NotificationBase):
    """No-op production fallback: records the notify attempt in logs.

    Actual device delivery is the send_expo_push call in
    _deliver_push/notify_user; this only covers the audit trail when no
    Expo token exists for the user.
    """

    async def send(self, title, message, player_ids=None, user_id=None) -> dict:
        log.info(
            "notify_log_only",
            user_id=str(user_id) if user_id else None,
            title=title,
            player_ids=len(player_ids or []),
        )
        return {"ok": True, "log_only": True}


_log_notifier = LogNotifier()
_test_notifier: NotificationBase | None = None


def set_notifier_for_tests(n: NotificationBase | None) -> None:
    global _test_notifier
    _test_notifier = n


def reset_notifier_for_tests() -> None:
    global _test_notifier
    _test_notifier = None


def get_notifier() -> NotificationBase:
    return _test_notifier if _test_notifier is not None else _log_notifier


async def _pref_enabled(db, user_id, event_key: str | None) -> bool:
    """Muted event types must never block a push on a lookup error, and an
    absent prefs row means enabled."""
    if event_key is None:
        return True
    try:
        from sqlalchemy import select

        from app.models.device import UserNotificationPref

        row = (
            (
                await db.execute(
                    select(UserNotificationPref.enabled).where(
                        UserNotificationPref.user_id == user_id,
                        UserNotificationPref.event_key == event_key,
                    )
                )
            )
            .scalars()
            .first()
        )
        return True if row is None else bool(row)
    except Exception as e:
        log.warning("pref_lookup_failed", user_id=str(user_id), error=str(e))
        return True


async def resolve_player_ids(db, user_id) -> list[str]:
    """Device ids subscribed by this user (call inside the request/session)."""
    from sqlalchemy import select

    from app.models.device import PushSubscription

    rows = (
        (await db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id)))
        .scalars()
        .all()
    )
    return [r.player_id for r in rows]


def schedule_push(
    player_ids: list[str],
    user_id: str,
    title: str,
    message: str,
    event_key: str | None = None,
) -> None:
    """Fire-and-forget push for the GPS hot path.

    Subscriptions must already be resolved with resolve_player_ids() inside
    the request; the actual 15s-timeout Expo HTTP send runs in a background
    task so a slow/hanging push endpoint can never add latency to the 1 Hz
    safety-critical GPS fix. Never raises.
    """
    task = asyncio.create_task(_deliver_push(player_ids, user_id, title, message, event_key))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _split_ids(player_ids: list[str]) -> tuple[list[str], list[str]]:
    """(deliverable Expo tokens, undeliverable other ids)."""
    from app.services.push_sender import is_expo_token

    expo = [p for p in player_ids if is_expo_token(p)]
    other = [p for p in player_ids if not is_expo_token(p)]
    return expo, other


async def _send_expo_or_log(
    player_ids: list[str], user_id: str, title: str, message: str
) -> dict:
    result = await get_notifier().send(title, message, player_ids=player_ids, user_id=user_id)
    expo_ids, other_ids = _split_ids(player_ids)
    for stale in other_ids:
        log.warning(
            "non_expo_player_id_skipped",
            user_id=str(user_id),
            player_id=stale[:12] + "…",
        )
    if expo_ids:
        try:
            from app.services.push_sender import send_expo_push

            result = {**result, "expo": await send_expo_push(expo_ids, title, message)}
        except Exception as e:
            log.warning("expo_push_skipped", error=str(e))
    return result


async def _deliver_push(
    player_ids: list[str],
    user_id: str,
    title: str,
    message: str,
    event_key: str | None = None,
) -> None:
    try:
        if event_key is not None:
            from app.db.session import get_session_factory

            factory = get_session_factory()
            async with factory() as session:
                if not await _pref_enabled(session, user_id, event_key):
                    log.info(
                        "notify_muted_by_pref",
                        user_id=str(user_id),
                        event_key=event_key,
                    )
                    return
        result = await _send_expo_or_log(player_ids, user_id, title, message)
        log.info("notify_user", user_id=user_id, title=title, result=str(result)[:200])
    except Exception as e:
        log.error("notify_user_failed", user_id=user_id, error=str(e))


async def notify_user(
    db, user_id, title: str, message: str, event_key: str | None = None
) -> dict:
    """Awaited push (start/stop flows). Never raises."""
    try:
        if not await _pref_enabled(db, user_id, event_key):
            log.info("notify_muted_by_pref", user_id=str(user_id), event_key=event_key)
            return {"ok": True, "muted": True}
        player_ids = await resolve_player_ids(db, user_id)
        result = await _send_expo_or_log(player_ids, str(user_id), title, message)
        log.info("notify_user", user_id=str(user_id), title=title, result=str(result)[:200])
        return result
    except Exception as e:
        log.error("notify_user_failed", user_id=str(user_id), error=str(e))
        return {"ok": False, "error": str(e)}
