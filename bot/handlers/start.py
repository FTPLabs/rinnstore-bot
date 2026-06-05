from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from ..keyboards.user import main_menu_kb, back_to_menu_kb
from ..services.settings_service import get_setting
from ..handlers.onboarding import start_onboarding

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear()
    shop_name = await get_setting(session, "shop_name")
    await start_onboarding(message, user, session, state, bot, shop_name)


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, user: User, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear()
    shop_name = await get_setting(session, "shop_name")
    await start_onboarding(call, user, session, state, bot, shop_name)
    await call.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery, user: User):
    ref = user.referral_code or "—"
    text = (
        f"<b>Профиль</b>\n\n"
        f"ID: <code>{user.id}</code>\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Потрачено: <b>{user.total_spent} ₽</b>\n"
        f"Баланс: <b>{user.balance} ₽</b>\n"
        f"Реф. код: <code>{ref}</code>\n"
        f"Дата: {user.created_at.strftime('%d.%m.%Y')}"
    )
    await call.message.edit_text(text, reply_markup=back_to_menu_kb())
    await call.answer()


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery, session: AsyncSession):
    username = await get_setting(session, "support_username")
    text = f"<b>Поддержка</b>\n\n@{username}"
    await call.message.edit_text(text, reply_markup=back_to_menu_kb())
    await call.answer()
