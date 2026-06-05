from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from ..models import User
from ..keyboards.user import main_menu_kb, back_to_menu_kb
from ..config import settings
from ..utils.emoji import STAR, SHIELD, KEY, SUPPORT, PROFILE, PROMO

router = Router()

WELCOME_TEXT = (
    f"<b>RINN STORE</b>\n\n"
    f"Цифровые товары · Оплата криптовалютой · Мгновенная выдача"
)


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, state: FSMContext):
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, user: User, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb())
    except Exception:
        await call.message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())
    await call.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery, user: User):
    text = (
        f"<b>Профиль</b>\n\n"
        f"ID: <code>{user.id}</code>\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Username: @{user.username or '—'}\n\n"
        f"Потрачено: <b>{user.total_spent} ₽</b>\n"
        f"Реф. код: <code>{user.referral_code}</code>\n"
        f"С нами с: {user.created_at.strftime('%d.%m.%Y')}"
    )
    await call.message.edit_text(text, reply_markup=back_to_menu_kb())
    await call.answer()


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    username = settings.support_username
    text = (
        f"<b>Поддержка</b>\n\n"
        f"По вопросам заказов: @{username}\n"
        f"Время ответа: до 24ч"
    )
    await call.message.edit_text(text, reply_markup=back_to_menu_kb())
    await call.answer()
