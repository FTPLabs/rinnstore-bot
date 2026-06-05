from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from ..services.user_service import get_or_create_user

_ONBOARDING_CALLBACKS = {
    "accept_terms", "refresh_captcha", "check_channel", "main_menu",
}
_ONBOARDING_PREFIXES = ("accept_", "refresh_", "check_")

_ONBOARDING_COMMANDS = {"/start"}


def _is_onboarding_event(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        if event.text and event.text.split()[0] in _ONBOARDING_COMMANDS:
            return True
        return False
    if isinstance(event, CallbackQuery):
        d = event.data or ""
        if d in _ONBOARDING_CALLBACKS:
            return True
        if any(d.startswith(p) for p in _ONBOARDING_PREFIXES):
            return True
    return False


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
                    await event.answer("Аккаунт заблокирован.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Аккаунт заблокирован.", show_alert=True)
                return

            if not _is_onboarding_event(event) and not user.terms_accepted:
                if isinstance(event, Message):
                    await event.answer("Для продолжения примите условия использования — отправьте /start")
                    return
                elif isinstance(event, CallbackQuery):
                    await event.answer("Сначала примите условия — отправьте /start", show_alert=True)
                    return

            if not _is_onboarding_event(event) and user.terms_accepted and not user.captcha_passed:
                if isinstance(event, Message):
                    await event.answer("Завершите регистрацию — отправьте /start")
                    return
                elif isinstance(event, CallbackQuery):
                    await event.answer("Завершите регистрацию — отправьте /start", show_alert=True)
                    return

        return await handler(event, data)
