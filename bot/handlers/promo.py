from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import PromoCode
from ..keyboards.user import back_to_menu_kb

router = Router()


class PromoStates(StatesGroup):
    waiting_code = State()


@router.callback_query(F.data == "promo")
async def cb_promo(call: CallbackQuery, state: FSMContext):
    await state.set_state(PromoStates.waiting_code)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu"))
    await call.message.edit_text(
        "🎟 <b>Введите промокод:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await call.answer()


@router.message(PromoStates.waiting_code)
async def process_promo_code(message: Message, session: AsyncSession, state: FSMContext):
    code = message.text.strip().upper()
    result = await session.execute(
        select(PromoCode).where(PromoCode.code == code, PromoCode.is_active == True)
    )
    promo = result.scalar_one_or_none()

    if not promo:
        await message.answer(
            "❌ Промокод не найден или недействителен.",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    if promo.max_uses and promo.used_count >= promo.max_uses:
        await message.answer(
            "❌ Промокод исчерпан.",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    if promo.expires_at and promo.expires_at.timestamp() < __import__("time").time():
        await message.answer(
            "❌ Промокод истёк.",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    discount_text = (
        f"{promo.discount_value}%" if promo.discount_type == "percent"
        else f"{promo.discount_value} руб."
    )

    data = await state.get_data()
    data["promo_code"] = code
    await state.set_data(data)

    await message.answer(
        f"✅ Промокод <b>{code}</b> применён!\n"
        f"💰 Скидка: <b>{discount_text}</b>\n\n"
        f"Скидка будет применена при оформлении следующего заказа.",
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML",
    )
    await state.set_state(None)
