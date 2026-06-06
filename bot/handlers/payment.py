from decimal import Decimal
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import User
from ..keyboards.user import payment_link_kb, back_to_menu_kb, order_detail_kb
from ..services.payment_service import (
    create_cryptobot_invoice, get_payment_by_order,
    check_cryptobot_invoice, mark_payment_paid
)
from ..services.order_service import get_order, deliver_order, cancel_order
from ..utils.helpers import parse_callback_int
from ..utils.emoji import KEY, OK, FAIL

router = Router()


@router.callback_query(F.data.startswith("pay_crypto_"))
async def cb_pay_crypto(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    order = await get_order(session, order_id)
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order.status != "pending":
        await call.answer("Заказ уже обработан", show_alert=True)
        return

    existing = await get_payment_by_order(session, order_id)
    if existing and existing.status == "pending" and existing.pay_url:
        await call.message.edit_text(
            f"<b>Оплата заказа #{order_id}</b>\n\nСумма: <b>{order.total_amount} ₽</b>",
            reply_markup=payment_link_kb(existing.pay_url, order_id),
        )
        await call.answer()
        return

    await call.answer("Создаю инвойс...")
    payment = await create_cryptobot_invoice(session, order)

    if not payment:
        await call.message.edit_text(
            "Ошибка создания платежа. Попробуйте позже.",
            reply_markup=back_to_menu_kb(),
        )
        return

    await call.message.edit_text(
        f"<b>Оплата заказа #{order_id}</b>\n\n"
        f"Сумма: <b>{order.total_amount} ₽</b>\n"
        f"К оплате: <b>{payment.amount} USDT</b>",
        reply_markup=payment_link_kb(payment.pay_url, order_id),
    )


@router.callback_query(F.data.startswith("pay_balance_"))
async def cb_pay_balance(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    order = await get_order(session, order_id)
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order.status != "pending":
        await call.answer("Заказ уже обработан", show_alert=True)
        return

    # FIX: with_for_update() — блокировка строки, исключает race condition двойного списания
    result = await session.execute(select(User).where(User.id == user.id).with_for_update())
    db_user = result.scalar_one_or_none()
    if not db_user:
        await call.answer("Ошибка пользователя", show_alert=True)
        return

    if db_user.balance < order.total_amount:
        await call.answer(
            f"Недостаточно средств. Баланс: {db_user.balance:.2f} ₽, нужно: {order.total_amount} ₽",
            show_alert=True
        )
        return

    # Списываем баланс
    db_user.balance -= order.total_amount
    db_user.total_spent = (db_user.total_spent or Decimal("0")) + order.total_amount
    order.status = "paid"
    await session.commit()

    # Выдаём товар
    delivered = await deliver_order(session, order_id)
    if not delivered:
        await call.answer("Ошибка выдачи товара. Напишите в поддержку.", show_alert=True)
        return

    items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
    await call.message.edit_text(
        f"{OK} <b>Оплачено с баланса!</b>\n\n{items_text}\n\nСохраните данные.",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer("✅ Оплата прошла")


@router.callback_query(F.data == "pay_rollypay_soon")
async def cb_rollypay_soon(call: CallbackQuery):
    await call.answer("RollyPay — скоро!", show_alert=True)


@router.callback_query(F.data.startswith("check_payment_"))
async def cb_check_payment(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    order = await get_order(session, order_id)
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return

    if order.status in ("paid", "delivered"):
        delivered = await deliver_order(session, order_id)
        if not delivered:
            await call.answer("Товары уже выданы или ошибка выдачи. Напишите в поддержку.", show_alert=True)
            return
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
        await call.message.edit_text(
            f"{OK} <b>Оплачено!</b>\n\n{items_text}\n\nСохраните данные.",
            reply_markup=back_to_menu_kb(),
        )
        await call.answer("✅ Оплата подтверждена")
        return

    payment = await get_payment_by_order(session, order_id)
    if not payment:
        await call.answer("Платёж не найден", show_alert=True)
        return

    status = await check_cryptobot_invoice(payment.provider_invoice_id)

    if status == "paid":
        await mark_payment_paid(session, payment)
        delivered = await deliver_order(session, order_id)
        if not delivered:
            await call.answer("Ошибка выдачи товара. Напишите в поддержку.", show_alert=True)
            return
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
        await call.message.edit_text(
            f"{OK} <b>Оплачено!</b>\n\n{items_text}\n\nСохраните данные.",
            reply_markup=back_to_menu_kb(),
        )
        await call.answer("✅ Оплата подтверждена")
    elif status == "expired":
        await call.answer("Время оплаты истекло. Создайте новый заказ.", show_alert=True)
    elif status == "active":
        await call.answer("Оплата ещё не поступила.", show_alert=True)
    elif status == "error":
        await call.answer("Ошибка проверки платежа. Попробуйте позже.", show_alert=True)
    else:
        await call.answer(f"Статус: {status}", show_alert=True)


@router.callback_query(F.data.startswith("cancel_order_"))
async def cb_cancel_order(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    order = await get_order(session, order_id)
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order.status not in ("pending",):
        await call.answer("Нельзя отменить этот заказ", show_alert=True)
        return

    await cancel_order(session, order_id)
    await call.message.edit_text(f"{FAIL} Заказ #{order_id} отменён", reply_markup=back_to_menu_kb())
    await call.answer("Отменён")
