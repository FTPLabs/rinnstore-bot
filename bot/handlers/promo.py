from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from datetime import datetime, timezone
from ..models import PromoCode
from ..keyboards.user import back_to_menu_kb

router = Router()


class UserPromoStates(StatesGroup):
    waiting_code = State()


@router.callback_query(F.data == "promo")
async def cb_promo(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserPromoStates.waiting_code)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="main_menu"))
    await call.message.edit_text("Введите промокод:", reply_markup=builder.as_markup())
    await call.answer()


@router.message(UserPromoStates.waiting_code)
async def process_promo_code(message: Message, session: AsyncSession, state: FSMContext):
    code = message.text.strip().upper()
    result = await session.execute(
        select(PromoCode).where(
            PromoCode.code == code,
            PromoCode.is_active == True,
            or_(PromoCode.expires_at == None, PromoCode.expires_at > datetime.now(timezone.utc)),
        )
    )
    promo = result.scalar_one_or_none()

    if not promo:
        await message.answer("Промокод не найден.", reply_markup=back_to_menu_kb())
        await state.clear()
        return

    if promo.max_uses and promo.used_count >= promo.max_uses:
        await message.answer("Промокод исчерпан.", reply_markup=back_to_menu_kb())
        await state.clear()
        return

    discount_text = (
        f"{promo.discount_value}%" if promo.discount_type == "percent"
        else f"{promo.discount_value} ₽"
    )

    data = await state.get_data()
    data["promo_code"] = code
    await state.set_data(data)
    await state.set_state(None)

    await message.answer(
        f"✅ Промокод <b>{code}</b> применён.\nСкидка: <b>{discount_text}</b>",
        reply_markup=back_to_menu_kb(),
    )
