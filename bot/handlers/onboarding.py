import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import User, Admin
from ..services.settings_service import get_setting
from ..keyboards.user import main_menu_kb, terms_kb, captcha_kb, channel_kb
from ..utils.captcha import generate_captcha

logger = logging.getLogger(__name__)

router = Router()


class OnboardingState(StatesGroup):
    captcha = State()


def _welcome_text(shop_name: str) -> str:
    return f"<b>{shop_name}</b>\nЦифровые товары · Крипто · Мгновенно"


async def _is_admin(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(Admin).where(Admin.user_id == user_id))
    return result.scalar_one_or_none() is not None


async def start_onboarding(
    message_or_call,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    shop_name: str = "RINN STORE",
):
    is_call = isinstance(message_or_call, CallbackQuery)
    msg = message_or_call.message if is_call else message_or_call

    if not user.terms_accepted:
        pp_url = await get_setting(session, "pp_url")
        tos_url = await get_setting(session, "tos_url")
        text = (
            f"<b>Добро пожаловать в {shop_name}</b>\n\n"
            f"Для использования бота примите условия:\n"
            f"· <a href='{tos_url}'>Пользовательское соглашение</a>\n"
            f"· <a href='{pp_url}'>Политика конфиденциальности</a>"
        )
        kb = terms_kb(pp_url, tos_url)
        try:
            if is_call:
                await msg.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
            else:
                await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)
        return

    if not user.captcha_passed:
        await send_captcha(msg, state)
        return

    channel = await get_setting(session, "required_channel")
    if channel:
        joined = await check_channel_member(bot, channel, user.id)
        if not joined:
            text = f"Для использования бота вступите в канал:"
            try:
                if is_call:
                    await msg.edit_text(text, reply_markup=channel_kb(channel))
                else:
                    await msg.answer(text, reply_markup=channel_kb(channel))
            except Exception:
                await msg.answer(text, reply_markup=channel_kb(channel))
            return

    is_adm = await _is_admin(session, user.id)
    text = _welcome_text(shop_name)
    kb = main_menu_kb(is_admin=is_adm)
    try:
        if is_call:
            await msg.edit_text(text, reply_markup=kb)
        else:
            await msg.answer(text, reply_markup=kb)
    except Exception:
        await msg.answer(text, reply_markup=kb)


async def send_captcha(msg: Message, state: FSMContext) -> None:
    buf, answer = generate_captcha()
    await state.set_state(OnboardingState.captcha)
    await state.update_data(captcha_answer=answer)
    photo = BufferedInputFile(buf.read(), filename="captcha.png")
    await msg.answer_photo(
        photo,
        caption="Введите цифры с картинки:",
        reply_markup=captcha_kb(),
    )


async def check_channel_member(bot: Bot, channel: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status not in ("left", "kicked", "restricted")
    except Exception as e:
        logger.warning(f"Channel check error for {channel}: {e}")
        return True


@router.callback_query(F.data == "accept_terms")
async def cb_accept_terms(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext, bot: Bot):
    user.terms_accepted = True
    await session.commit()
    await call.answer("Принято!")
    await send_captcha(call.message, state)


@router.message(OnboardingState.captcha)
async def handle_captcha_answer(message: Message, session: AsyncSession, user: User, state: FSMContext, bot: Bot):
    data = await state.get_data()
    correct = data.get("captcha_answer", "")
    if message.text and message.text.strip() == correct:
        user.captcha_passed = True
        await session.commit()
        await state.clear()

        shop_name = await get_setting(session, "shop_name")
        channel = await get_setting(session, "required_channel")
        if channel:
            joined = await check_channel_member(bot, channel, user.id)
            if not joined:
                await message.answer(
                    "Вступите в канал для продолжения:",
                    reply_markup=channel_kb(channel),
                )
                return

        is_adm = await _is_admin(session, user.id)
        await message.answer(_welcome_text(shop_name), reply_markup=main_menu_kb(is_admin=is_adm))
    else:
        await state.clear()
        buf, answer = generate_captcha()
        await state.set_state(OnboardingState.captcha)
        await state.update_data(captcha_answer=answer)
        photo = BufferedInputFile(buf.read(), filename="captcha.png")
        await message.answer_photo(photo, caption="Неверно. Попробуйте снова:", reply_markup=captcha_kb())


@router.callback_query(F.data == "refresh_captcha")
async def cb_refresh_captcha(call: CallbackQuery, state: FSMContext):
    buf, answer = generate_captcha()
    await state.set_state(OnboardingState.captcha)
    await state.update_data(captcha_answer=answer)
    photo = BufferedInputFile(buf.read(), filename="captcha.png")
    await call.message.answer_photo(photo, caption="Введите цифры с картинки:", reply_markup=captcha_kb())
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "check_channel")
async def cb_check_channel(call: CallbackQuery, session: AsyncSession, user: User, bot: Bot):
    channel = await get_setting(session, "required_channel")
    if not channel:
        await call.answer()
        shop_name = await get_setting(session, "shop_name")
        is_adm = await _is_admin(session, user.id)
        try:
            await call.message.edit_text(_welcome_text(shop_name), reply_markup=main_menu_kb(is_admin=is_adm))
        except Exception:
            await call.message.answer(_welcome_text(shop_name), reply_markup=main_menu_kb(is_admin=is_adm))
        return

    joined = await check_channel_member(bot, channel, user.id)
    if joined:
        await call.answer("Подписка подтверждена!")
        shop_name = await get_setting(session, "shop_name")
        is_adm = await _is_admin(session, user.id)
        try:
            await call.message.edit_text(_welcome_text(shop_name), reply_markup=main_menu_kb(is_admin=is_adm))
        except Exception:
            await call.message.answer(_welcome_text(shop_name), reply_markup=main_menu_kb(is_admin=is_adm))
    else:
        await call.answer("Вы ещё не вступили в канал.", show_alert=True)
