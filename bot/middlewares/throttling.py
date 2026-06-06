from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
import time
import logging

logger = logging.getLogger(__name__)

_MAX_CACHE_SIZE = 10_000


class ThrottlingMiddleware(BaseMiddleware):
    """Ограничивает частоту запросов. Хранение в памяти с автоочисткой."""

    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self._last_call: dict[int, float] = {}

    def _evict_old(self, now: float) -> None:
        """Удаляем записи старше 60 секунд, если кэш слишком большой."""
        if len(self._last_call) > _MAX_CACHE_SIZE:
            cutoff = now - 60
            stale = [uid for uid, ts in self._last_call.items() if ts < cutoff]
            for uid in stale:
                del self._last_call[uid]

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None

        if user_id is not None:
            now = time.monotonic()
            last = self._last_call.get(user_id, 0.0)
            if now - last < self.rate_limit:
                if isinstance(event, CallbackQuery):
                    await event.answer()
                return
            self._last_call[user_id] = now
            self._evict_old(now)

        return await handler(event, data)
