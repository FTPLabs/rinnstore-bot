from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from ..models import User
from ..keyboards.user import main_menu_kb, back_to_menu_kb
from ..utils.emoji import (
    STAR, SHIELD, KEY, SUPPORT, CATALOG, BACK, OK, PROFILE, PROMO
)

router = Router()

WELCOME_TEXT = (
    f"{STAR} <b>Добро пожаловать в Digital Shop!</b>\n\n"
    f"Здесь вы можете купить цифровые товары:\n"
    f"{KEY} Ключи и активации\n"
    f"{SHIELD} Аккаунты и подписки\n"
    f"{STAR} Эксклюзивный контент\n\n"
    f"{OK} Оплата — криптовалюта через CryptoBot\n"
    f"{KEY} Выдача — автоматически после оплаты\n"
    f"{SUPPORT} Поддержка — всегда на связи\n"
)


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, state: FSMContext):
    await state.clear()
    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, user: User, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text(
            WELCOME_TEXT,
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
    except Exception:
        await call.message.answer(
            WELCOME_TEXT,
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
    await call.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery, user: User):
    from ..utils.emoji import USERS, LOG, CATALOG, SEP
    from ..utils.emoji import SEP
    text = (
        f"{PROFILE} <b>Ваш профиль</b>\n"
        f"{'━' * 16}\n"
        f"{SHIELD} ID: <code>{user.id}</code>\n"
        f"{PROFILE} Имя: {user.first_name or '—'}\n"
        f"{PROFILE} Username: @{user.username or '—'}\n"
        f"{'━' * 16}\n"
        f"{STAR} Потрачено: <b>{user.total_spent} руб.</b>\n"
        f"{PROMO} Реф. код: <code>{user.referral_code}</code>\n"
        f"{'━' * 16}\n"
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y')}"
    )
    await call.message.edit_text(
        text,
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    from ..utils.emoji import SUPPORT, SHIELD, ALERT
    text = (
        f"{SUPPORT} <b>Поддержка</b>\n"
        f"{'━' * 16}\n\n"
        f"Если у вас возникли проблемы с заказом — напишите нам.\n\n"
        f"{SHIELD} Мы защищаем каждую покупку\n"
        f"{ALERT} Среднее время ответа: до 24 часов\n\n"
        f"<b>Контакты:</b>\n"
        f"📧 @support_username"
    )
    await call.message.edit_text(
        text,
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML"
    )
    await call.answer()
