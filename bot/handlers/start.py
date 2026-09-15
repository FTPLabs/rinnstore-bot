from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User, Admin
from ..keyboards.user import main_menu_kb, back_to_menu_kb, profile_kb
from ..utils.i18n import t
from ..services.settings_service import get_setting
from ..services.user_service import get_referral_count, get_or_create_user
from ..handlers.onboarding import start_onboarding
from ..utils.emoji import (
    PROFILE, USER, ATTACH, COINS, BAG, GIFT, LINK, SUPPORT, SETTINGS,
    ID_CARD, CROWN, TIMER, plain,
)

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


@router.callback_query(F.data == "language")
async def cb_language(call: CallbackQuery, user: User):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Русский", callback_data="set_language_ru", style="primary"), InlineKeyboardButton(text="English", callback_data="set_language_en", style="primary"))
    builder.row(InlineKeyboardButton(text=f"◀️ {t(user, 'back')}", callback_data="main_menu", style="primary"))
    await call.message.edit_text(t(user, "choose_language"), reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data.regexp(r"^set_language_(ru|en)$"))
async def cb_set_language(call: CallbackQuery, user: User, session: AsyncSession, state: FSMContext, bot: Bot):
    user.language_code = call.data.rsplit("_", 1)[-1]
    await session.commit()
    await call.answer(t(user, "language_changed"))
    shop_name = await get_setting(session, "shop_name")
    await start_onboarding(call, user, session, state, bot, shop_name)


@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery, user: User, session: AsyncSession, bot: Bot):
    ref = user.referral_code or "—"
    bot_username = await get_bot_username(bot)
    ref_link = f"https://t.me/{bot_username}?start={ref}"
    ref_count = await get_referral_count(session, user.id)
    is_admin = await _is_admin(session, user.id)

    reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "—"
    username_str = f"@{user.username}" if user.username else "—"

    level = "Новичок"
    if user.total_spent >= 10000:
        level = "VIP"
    elif user.total_spent >= 3000:
        level = "Постоянный"

    referral_bonus_str = f"{user.referral_bonus:.2f}" if user.referral_bonus else "0.00"

    text = (
        f"{PROFILE} <b>ПРОФИЛЬ</b>\n"
        f"{'━' * 20}\n\n"
        f"{ID_CARD} <b>ID:</b> <code>{user.id}</code>\n"
        f"{USER} <b>Имя:</b> {user.first_name or '—'}\n"
        f"{ATTACH} <b>Username:</b> {username_str}\n"
        f"{CROWN} <b>Уровень:</b> {level}\n"
        f"{TIMER} <b>Регистрация:</b> {reg_date}\n\n"
        f"{'━' * 20}\n"
        f"{COINS} <b>Баланс: {user.balance:.2f} ₽</b>\n"
        f"{BAG} <b>Потрачено: {user.total_spent:.2f} ₽</b>\n"
        f"{GIFT} <b>Реф. бонус: {referral_bonus_str} ₽</b>\n\n"
        f"{'━' * 20}\n"
        f"{LINK} <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n"
        f"<b>Приглашено друзей: {ref_count}</b>\n"
        f"<b>Ваш код:</b> <code>{ref}</code>\n"
        f"<b>Ссылка:</b> <code>{ref_link}</code>"
    )
    if is_admin:
        text += f"\n\n{'━' * 20}\n{SETTINGS} Роль: <b>Администратор</b>"

    await call.message.edit_text(text, reply_markup=profile_kb(ref, bot_username), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery, session: AsyncSession):
    username = await get_setting(session, "support_username")
    text = f"<b>{SUPPORT} Поддержка</b>\n\nПишите нам: @{username}"
    await call.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await call.answer()
