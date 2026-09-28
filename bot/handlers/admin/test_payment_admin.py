"""Admin-only FreeKassa test payment for exactly 1 RUB."""
from __future__ import annotations

import html
from decimal import Decimal
from email.utils import parseaddr

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...keyboards.user import back_to_menu_kb
from ...models import Order, Payment, User
from ...services.admin_service import is_admin, log_action
from ...services.freekassa_service import (
    check_freekassa_invoice,
    create_freekassa_invoice,
    get_freekassa_currencies,
    is_freekassa_api_enabled,
)
from ...services.payment_service import mark_payment_paid
from ...utils.emoji import FAIL, OK, plain

router = Router()
TEST_AMOUNT = Decimal("1.00")
TEST_NOTE = "admin_freekassa_test_payment"


class TestPaymentState(StatesGroup):
    waiting_email = State()


def _cancel_kb() -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_main"))
    return builder.as_markup()


def _methods_kb(currencies: list[dict]) -> object:
    builder = InlineKeyboardBuilder()
    for item in currencies[:12]:
        try:
            currency_id = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        currency = str(item.get("currency") or "").upper()
        if currency != "RUB":
            continue
        name = str(item.get("name") or f"Способ {currency_id}")
        builder.row(InlineKeyboardButton(
            text=f"{name} ({currency})",
            callback_data=f"admin_test_fk_{currency_id}_{currency}",
            style="primary",
        ))
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_main"))
    return builder.as_markup()


def _payment_kb(pay_url: str, order_id: int) -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Оплатить 1 ₽", url=pay_url, style="primary"))
    builder.row(InlineKeyboardButton(
        text=f"{plain(OK)} Проверить тестовый платёж",
        callback_data=f"admin_test_check_{order_id}", style="success",
    ))
    builder.row(InlineKeyboardButton(text="Назад", callback_data="admin_main"))
    return builder.as_markup()


@router.callback_query(F.data == "admin_test_payment")
async def cb_test_payment(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    if not is_freekassa_api_enabled():
        await call.message.edit_text(
            f"{FAIL} FreeKassa не настроена. Нужны Shop ID, API Key и публичный IP сервера.",
            reply_markup=_cancel_kb(), parse_mode="HTML",
        )
        return await call.answer()
    currencies = [
        item for item in await get_freekassa_currencies()
        if str(item.get("currency") or "").upper() == "RUB"
    ]
    if not currencies:
        await call.message.edit_text(
            f"{FAIL} FreeKassa не вернула доступные способы оплаты RUB.",
            reply_markup=_cancel_kb(), parse_mode="HTML",
        )
        return await call.answer()
    await call.message.edit_text(
        "<b>Тестовый платёж FreeKassa</b>\n\n"
        "Сумма фиксирована: <b>1.00 ₽</b>.\n"
        "Выберите способ оплаты:",
        reply_markup=_methods_kb(currencies), parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^admin_test_fk_\d+_[A-Z]{3}$"))
async def cb_test_payment_method(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    _, _, _, currency_id_raw, currency = call.data.split("_", 4)
    await state.update_data(test_currency_id=int(currency_id_raw), test_currency=currency)
    await state.set_state(TestPaymentState.waiting_email)
    await call.message.edit_text(
        "Введите e-mail плательщика для тестового счёта FreeKassa:",
        reply_markup=_cancel_kb(),
    )
    await call.answer()


@router.message(TestPaymentState.waiting_email, F.text)
async def msg_test_payment_email(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    email = message.text.strip()
    if parseaddr(email)[1] != email or "@" not in email:
        await message.answer("Введите корректный e-mail.")
        return
    data = await state.get_data()
    currency_id = data.get("test_currency_id")
    currency = data.get("test_currency", "RUB")
    if not currency_id:
        await state.clear()
        await message.answer("Сессия тестового платежа истекла. Запустите её заново.")
        return

    order = Order(
        user_id=user.id,
        status="pending",
        total_amount=TEST_AMOUNT,
        currency="RUB",
        notes=TEST_NOTE,
    )
    session.add(order)
    await session.flush()
    payment = await create_freekassa_invoice(
        session, order, payer_email=email,
        currency_id=int(currency_id), currency=str(currency),
    )
    if not payment:
        await session.rollback()
        await state.clear()
        await message.answer(
            f"{FAIL} Не удалось создать тестовый счёт FreeKassa.",
            reply_markup=back_to_menu_kb(user.language_code),
        )
        return

    await log_action(session, user.id, "create_test_payment", "payment", payment.id, {
        "order_id": order.id, "amount": "1.00", "currency": currency,
    })
    await state.clear()
    await message.answer(
        f"{OK} <b>Тестовый счёт создан</b>\n\n"
        f"Заказ: <code>#{order.id}</code>\n"
        f"Сумма: <b>1.00 ₽</b>\n"
        f"Способ: <b>{html.escape(str(currency))}</b>\n\n"
        "Откройте оплату, затем нажмите «Проверить тестовый платёж». "
        "Товар и отзыв по этому счёту не создаются.",
        reply_markup=_payment_kb(payment.pay_url, order.id), parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_test_check_"))
async def cb_check_test_payment(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    try:
        order_id = int(call.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Order).where(
        Order.id == order_id, Order.user_id == user.id, Order.notes == TEST_NOTE,
    ))
    order = result.scalar_one_or_none()
    if not order:
        return await call.answer("Тестовый заказ не найден", show_alert=True)
    payment_result = await session.execute(select(Payment).where(
        Payment.order_id == order.id, Payment.provider == "freekassa",
    ).order_by(Payment.id.desc()))
    payment = payment_result.scalars().first()
    if not payment:
        return await call.answer("Счёт не найден", show_alert=True)
    status = await check_freekassa_invoice(payment)
    if status == "paid":
        if payment.status != "paid":
            await mark_payment_paid(session, payment)
        await call.message.edit_text(
            f"{OK} <b>Тестовый платёж подтверждён</b>\n\n"
            f"Счёт <code>#{order.id}</code> на <b>1.00 ₽</b> успешно оплачен.\n"
            "Выдача товара и запрос отзыва не выполняются.",
            reply_markup=back_to_menu_kb(user.language_code), parse_mode="HTML",
        )
        await call.answer("Оплата подтверждена")
    elif status == "pending":
        await call.answer("Оплата ещё не поступила", show_alert=True)
    elif status == "failed":
        await call.answer("Тестовый платёж отклонён или истёк", show_alert=True)
    else:
        await call.answer("Не удалось проверить FreeKassa", show_alert=True)
