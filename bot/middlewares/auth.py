from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from ..services.user_service import get_or_create_user


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession = data.get("session")
        tg_user = None

        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if tg_user and session:
            user = await get_or_create_user(session, tg_user)
            data["user"] = user
            if user.is_banned:
                if isinstance(event, Message):
                    await event.answer("🚫 Ваш аккаунт заблокирован.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 Ваш аккаунт заблокирован.", show_alert=True)
                return
        return await handler(event, data)
