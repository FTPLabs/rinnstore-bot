from decimal import Decimal, InvalidOperation
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...models import User, PromoCode
from ...keyboards.admin import admin_promos_kb, admin_promo_detail_kb, cancel_kb
from ...services.admin_service import is_admin, get_all_promos, create_promo, toggle_promo, log_action
from ...utils.emoji import (
    PROMO, ADD, OK, FAIL, BACK, STATS, TAG
)

router = Router()


class PromoStates(StatesGroup):
    waiting_code = State()
    waiting_discount_type = State()
    waiting_discount_value = State()
    waiting_max_uses = State()


@router.callback_query(F.data == "admin_promos")
async def cb_admin_promos(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    promos = await get_all_promos(session)
    text = (
        f"{PROMO} <b>Промокоды</b>\n"
        f"{'━' * 16}\n\n"
        f"Всего: <b>{len(promos)}</b>"
    )
    await call.message.edit_text(text, reply_markup=admin_promos_kb(promos), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("admin_promo_") & ~F.data.startswith("admin_promo_toggle_"))
async def cb_admin_promo_detail(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    promo_id = int(call.data.split("_")[2])
    result = await session.execute(select(PromoCode).where(PromoCode.id == promo_id))
    promo = result.scalar_one_or_none()
    if not promo:
        return await call.answer("Промокод не найден", show_alert=True)

    val = f"{promo.discount_value}%" if promo.discount_type == "percent" else f"{promo.discount_value} руб."
    status = f"{OK} Активен" if promo.is_active else f"{FAIL} Отключён"
    expires = promo.expires_at.strftime("%d.%m.%Y") if promo.expires_at else "Без срока"
    text = (
        f"{PROMO} <b>{promo.code}</b>\n"
        f"{'━' * 16}\n\n"
        f"📌 Статус: {status}\n"
        f"💰 Скидка: <b>{val}</b>\n"
        f"{STATS} Использований: <b>{promo.used_count}</b>"
        + (f" / {promo.max_uses}" if promo.max_uses else "") + "\n"
        f"⏰ Истекает: {expires}"
    )
    await call.message.edit_text(
        text,
        reply_markup=admin_promo_detail_kb(promo_id, promo.is_active),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_toggle_promo_"))
async def cb_toggle_promo(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    promo_id = int(call.data.split("_")[3])
    new_status = await toggle_promo(session, promo_id)
    await log_action(session, user.id, "toggle_promo", "promo", promo_id, {"active": new_status})
    await call.answer(f"Промокод {'активирован' if new_status else 'деактивирован'}", show_alert=True)
    call.data = f"admin_promo_{promo_id}"
    await cb_admin_promo_detail(call, session, user)


@router.callback_query(F.data == "admin_add_promo")
async def cb_admin_add_promo(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.set_state(PromoStates.waiting_code)
    await call.message.edit_text(
        f"{ADD} <b>Новый промокод</b>\n\nВведите код (только латиница и цифры):\n\n"
        f"Пример: <code>SALE20</code>",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(PromoStates.waiting_code)
async def process_promo_code_admin(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if not code.replace("-", "").isalnum():
        await message.answer(f"{FAIL} Код должен содержать только буквы и цифры.")
        return
    await state.update_data(promo_code=code)
    await state.set_state(PromoStates.waiting_discount_type)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="% Процент", callback_data="promo_type_percent"),
        InlineKeyboardButton(text="₽ Фиксированная", callback_data="promo_type_fixed"),
    )
    await message.answer(
        f"{PROMO} Выберите тип скидки:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.in_({"promo_type_percent", "promo_type_fixed"}), PromoStates.waiting_discount_type)
async def process_promo_type(call: CallbackQuery, state: FSMContext):
    dtype = "percent" if call.data == "promo_type_percent" else "fixed"
    await state.update_data(discount_type=dtype)
    await state.set_state(PromoStates.waiting_discount_value)
    hint = "процентов (1-100)" if dtype == "percent" else "рублей"
    await call.message.edit_text(
        f"💰 Введите размер скидки в {hint}:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(PromoStates.waiting_discount_value)
async def process_promo_value(message: Message, state: FSMContext):
    try:
        val = Decimal(message.text.strip())
        if val <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer(f"{FAIL} Введите число больше 0")
        return
    await state.update_data(discount_value=val)
    await state.set_state(PromoStates.waiting_max_uses)
    await message.answer(
        "🔢 Максимум использований (введите число или «0» для неограниченного):"
    )


@router.message(PromoStates.waiting_max_uses)
async def process_promo_max_uses(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        max_uses = int(message.text.strip())
    except ValueError:
        await message.answer(f"{FAIL} Введите целое число")
        return
    data = await state.get_data()
    promo = await create_promo(
        session,
        code=data["promo_code"],
        discount_type=data["discount_type"],
        discount_value=data["discount_value"],
        max_uses=max_uses if max_uses > 0 else None,
    )
    await log_action(session, user.id, "create_promo", "promo", promo.id)
    await state.clear()
    val = f"{promo.discount_value}%" if promo.discount_type == "percent" else f"{promo.discount_value} руб."
    await message.answer(
        f"{OK} <b>Промокод создан!</b>\n\n"
        f"{PROMO} Код: <code>{promo.code}</code>\n"
        f"💰 Скидка: <b>{val}</b>",
        parse_mode="HTML"
    )
