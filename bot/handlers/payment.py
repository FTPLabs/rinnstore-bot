from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import User
from ..keyboards.user import payment_link_kb, back_to_menu_kb, order_detail_kb
from ..services.payment_service import (
    create_cryptobot_invoice, get_payment_by_order,
    check_cryptobot_invoice, mark_payment_paid
)
from ..services.order_service import get_order, deliver_order, cancel_order
from ..utils.emoji import (
    SHIELD, KEY, OK, FAIL, BACK, CLOCK, STAR, BAG, REFRESH
)

router = Router()


@router.callback_query(F.data.startswith("pay_crypto_"))
async def cb_pay_crypto(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = int(call.data.split("_")[2])
    order = await get_order(session, order_id)

    if not order or order.user_id != user.id:
        await call.answer("❌ Заказ не найден", show_alert=True)
        return

    if order.status != "pending":
        await call.answer("⚠️ Заказ уже обработан", show_alert=True)
        return

    existing = await get_payment_by_order(session, order_id)
    if existing and existing.status == "pending" and existing.pay_url:
        await call.message.edit_text(
            f"{SHIELD} <b>Оплата заказа #{order_id}</b>\n"
            f"{'━' * 16}\n\n"
            f"💰 Сумма: <b>{order.total_amount} руб.</b>\n\n"
            f"{CLOCK} Инвойс уже создан. Оплатите по ссылке ниже:",
            reply_markup=payment_link_kb(existing.pay_url, order_id),
            parse_mode="HTML",
        )
        await call.answer()
        return

    await call.answer("⏳ Создаю инвойс...")
    payment = await create_cryptobot_invoice(session, order)

    if not payment:
        await call.message.edit_text(
            f"{FAIL} <b>Ошибка создания платежа</b>\n\n"
            f"Не удалось создать инвойс. Попробуйте позже или обратитесь в поддержку.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        return

    await call.message.edit_text(
        f"{SHIELD} <b>Оплата заказа #{order_id}</b>\n"
        f"{'━' * 16}\n\n"
        f"💰 Сумма: <b>{order.total_amount} руб.</b>\n"
        f"{STAR} К оплате: <b>{payment.amount} USDT</b>\n\n"
        f"Нажмите кнопку и оплатите через CryptoBot.\n"
        f"После оплаты нажмите «{REFRESH} Проверить оплату».",
        reply_markup=payment_link_kb(payment.pay_url, order_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "pay_rollypay_soon")
async def cb_rollypay_soon(call: CallbackQuery):
    await call.answer("💳 RollyPay будет подключён в ближайшее время!", show_alert=True)


@router.callback_query(F.data.startswith("check_payment_"))
async def cb_check_payment(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = int(call.data.split("_")[2])
    order = await get_order(session, order_id)

    if not order or order.user_id != user.id:
        await call.answer("❌ Заказ не найден", show_alert=True)
        return

    if order.status in ("paid", "delivered"):
        delivered = await deliver_order(session, order_id)
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
        await call.message.edit_text(
            f"{OK} <b>Оплата подтверждена!</b>\n"
            f"{'━' * 16}\n\n"
            f"{BAG} <b>Ваши товары:</b>\n{items_text}\n\n"
            f"{STAR} Спасибо за покупку! Сохраните данные.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer("✅ Оплата подтверждена!")
        return

    payment = await get_payment_by_order(session, order_id)
    if not payment:
        await call.answer("❌ Платёж не найден", show_alert=True)
        return

    status = await check_cryptobot_invoice(payment.provider_invoice_id)

    if status == "paid":
        await mark_payment_paid(session, payment)
        delivered = await deliver_order(session, order_id)
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
        await call.message.edit_text(
            f"{OK} <b>Оплата подтверждена!</b>\n"
            f"{'━' * 16}\n\n"
            f"{BAG} <b>Ваши товары:</b>\n{items_text}\n\n"
            f"{STAR} Спасибо за покупку! Сохраните данные.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer("✅ Оплата подтверждена!")
    elif status == "expired":
        await call.answer("⏰ Время оплаты истекло. Создайте новый заказ.", show_alert=True)
    elif status == "active":
        await call.answer("⏳ Оплата ещё не поступила. Попробуйте через минуту.", show_alert=True)
    else:
        await call.answer(f"Статус: {status}", show_alert=True)


@router.callback_query(F.data.startswith("cancel_order_"))
async def cb_cancel_order(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = int(call.data.split("_")[2])
    order = await get_order(session, order_id)

    if not order or order.user_id != user.id:
        await call.answer("❌ Заказ не найден", show_alert=True)
        return

    if order.status not in ("pending",):
        await call.answer("⚠️ Нельзя отменить этот заказ", show_alert=True)
        return

    await cancel_order(session, order_id)
    await call.message.edit_text(
        f"{FAIL} <b>Заказ #{order_id} отменён</b>",
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML",
    )
    await call.answer("❌ Заказ отменён")
