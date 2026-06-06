from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User, Admin
from ..keyboards.user import main_menu_kb, back_to_menu_kb, profile_kb
from ..services.settings_service import get_setting
from ..services.user_service import get_referral_count, get_or_create_user
from ..handlers.onboarding import start_onboarding

router = Router()

_bot_username_cache: str | None = None


async def get_bot_username(bot: Bot) -> str:
    global _bot_username_cache
    if not _bot_username_cache:
        me = await bot.get_me()
        _bot_username_cache = me.username
    return _bot_username_cache


async def _is_admin(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(Admin).where(Admin.user_id == user_id))
    return result.scalar_one_or_none() is not None


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear()

    args = message.text.split(maxsplit=1)
    if len(args) > 1 and user.referred_by is None:
        ref_code = args[1].strip()
        if ref_code and ref_code != user.referral_code:
            result = await session.execute(select(User).where(User.referral_code == ref_code.upper()))
            referrer = result.scalar_one_or_none()
            if referrer and referrer.id != user.id:
                user.referred_by = referrer.id
                await session.commit()

    shop_name = await get_setting(session, "shop_name")
    await start_onboarding(message, user, session, state, bot, shop_name)


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, user: User, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear()
    shop_name = await get_setting(session, "shop_name")
    await start_onboarding(call, user, session, state, bot, shop_name)
    await call.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery, user: User, session: AsyncSession, bot: Bot):
    ref = user.referral_code or "—"
    bot_username = await get_bot_username(bot)
    ref_link = f"https://t.me/{bot_username}?start={ref}"
    ref_count = await get_referral_count(session, user.id)
    is_admin = await _is_admin(session, user.id)

    reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "—"
    username_str = f"@{user.username}" if user.username else "—"

    level = "🥉 Новичок"
    if user.total_spent >= 10000:
        level = "🥇 VIP"
    elif user.total_spent >= 3000:
        level = "🥈 Постоянный"

    referral_bonus_str = f"{user.referral_bonus:.2f}" if user.referral_bonus else "0.00"

    text = (
        f"<b>👤 Профиль</b>\n"
        f"{'━' * 20}\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Имя: {user.first_name or '—'}\n"
        f"📎 Username: {username_str}\n"
        f"🏅 Уровень: {level}\n"
        f"📅 Регистрация: {reg_date}\n\n"
        f"{'━' * 20}\n"
        f"💰 Баланс: <b>{user.balance:.2f} ₽</b>\n"
        f"🛍 Потрачено: <b>{user.total_spent:.2f} ₽</b>\n"
        f"🎁 Реф. бонус: <b>{referral_bonus_str} ₽</b>\n\n"
        f"{'━' * 20}\n"
        f"🔗 Реф. программа\n"
        f"Приглашено друзей: <b>{ref_count}</b>\n"
        f"Ваш код: <code>{ref}</code>\n"
        f"Ссылка: <code>{ref_link}</code>"
    )
    if is_admin:
        text += f"\n\n{'━' * 20}\n⚙️ Роль: <b>Администратор</b>"

    await call.message.edit_text(text, reply_markup=profile_kb(ref, bot_username), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery, session: AsyncSession):
    username = await get_setting(session, "support_username")
    text = f"<b>💬 Поддержка</b>\n\nПишите нам: @{username}"
    await call.message.edit_text(text, reply_markup=back_to_menu_kb())
    await call.answer()
