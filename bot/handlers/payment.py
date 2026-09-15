from decimal import Decimal
import html
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import User, Payment, Order
from ..keyboards.user import payment_link_kb, back_to_menu_kb, order_detail_kb
from ..services.payment_service import (
    create_cryptobot_invoice, get_payment_by_order, get_payment_by_order_provider,
    get_payment_for_check, check_cryptobot_invoice, mark_payment_paid,
    create_rollypay_invoice, check_rollypay_payment,
)
from ..services.order_service import get_order, deliver_order, cancel_order
from ..utils.helpers import parse_callback_int
from ..utils.emoji import KEY, OK, FAIL, WARN, CARD, COINS, plain
from ..config import settings as env_settings

router = Router()


@router.callback_query(F.data.startswith("pay_stars_"))
async def cb_pay_stars(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return
    result = await session.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    if not order or order.user_id != user.id or order.status != "pending":
        await call.answer("Заказ недоступен", show_alert=True)
        return
    amount = max(1, int(Decimal(str(order.total_amount)).to_integral_value()))
    payload = f"stars:{order.id}:{user.id}:{amount}"
    existing = await session.execute(select(Payment).where(
        Payment.order_id == order.id, Payment.provider == "telegram_stars", Payment.status == "pending"
    ).order_by(Payment.id.desc()))
    payment = existing.scalars().first()
    if not payment:
        payment = Payment(order_id=order.id, provider="telegram_stars", provider_invoice_id=payload,
                          amount=amount, currency="XTR", status="pending", payload={"amount": amount})
        session.add(payment)
        await session.commit()
    await call.message.answer_invoice(
        title=f"Заказ #{order.id}", description="RINN STORE",
        payload=payload, currency="XTR", provider_token="",
        prices=[LabeledPrice(label=f"Заказ #{order.id}", amount=amount)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, session: AsyncSession):
    parts = (query.invoice_payload or "").split(":")
    if len(parts) != 4 or parts[0] != "stars":
        await query.answer(ok=False, error_message="Некорректный платёж")
        return
    try:
        order_id, user_id, amount = map(int, parts[1:])
    except ValueError:
        await query.answer(ok=False, error_message="Некорректные данные заказа")
        return
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if (not order or order.user_id != user_id or query.from_user.id != user_id
            or order.status != "pending" or query.currency != "XTR" or query.total_amount != amount):
        await query.answer(ok=False, error_message="Заказ уже недоступен")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_stars(message: Message, session: AsyncSession, user: User):
    payment_data = message.successful_payment
    parts = (payment_data.invoice_payload or "").split(":")
    if len(parts) != 4 or parts[0] != "stars":
        return
    try:
        order_id, user_id, amount = map(int, parts[1:])
    except ValueError:
        return
    if user.id != user_id or payment_data.currency != "XTR" or payment_data.total_amount != amount:
        return
    result = await session.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    if not order:
        return
    charge_id = payment_data.telegram_payment_charge_id
    existing = await session.execute(select(Payment).where(Payment.provider_invoice_id == charge_id))
    if existing.scalar_one_or_none():
        return
    pay_result = await session.execute(select(Payment).where(
        Payment.order_id == order_id, Payment.provider == "telegram_stars"
    ).order_by(Payment.id.desc()).with_for_update())
    payment = pay_result.scalars().first()
    if not payment or order.status != "pending":
        return
    payment.provider_invoice_id = charge_id
    payment.status = "paid"
    payment.amount = amount
    payment.currency = "XTR"
    order.status = "paid"
    await session.commit()
    delivered = await deliver_order(session, order_id)
    if delivered:
        items = "\n".join(f"{KEY} <code>{html.escape(str(d['data']))}</code>" for d in delivered)
        await message.answer(f"{OK} <b>Оплата Stars прошла!</b>\n\n{items}", parse_mode="HTML")


def _get_webhook_host() -> str:
    from ..services.settings_service import get_cached
    host = get_cached("webhook_host") or env_settings.webhook_host
    return host.rstrip("/") if host else ""


def _parse_check_payment(data: str) -> tuple[int | None, str]:
    prefix = "check_payment_"
    if not data.startswith(prefix):
        return None, "crypto"
    rest = data[len(prefix):]
    parts = rest.split("_", 1)
    try:
        order_id = int(parts[0])
    except (ValueError, IndexError):
        return None, "crypto"
    provider = parts[1] if len(parts) > 1 else "crypto"
    return order_id, provider


# ── CRYPTOBOT ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_crypto_"))
async def cb_pay_crypto(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    result = await session.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order.status != "pending":
        await call.answer("Заказ уже обработан", show_alert=True)
        return

    existing = await get_payment_by_order_provider(session, order_id, "cryptobot")
    if existing and existing.pay_url:
        await call.message.edit_text(
            f"<b>Оплата заказа #{order_id}</b>\n\nСумма: <b>{order.total_amount} ₽</b>",
            reply_markup=payment_link_kb(existing.pay_url, order_id, "crypto"),
            parse_mode="HTML",
        )
        await call.answer()
        return

    await call.answer("Создаю инвойс...")
    payment = await create_cryptobot_invoice(session, order)

    if not payment:
        await call.message.edit_text(
            f"{FAIL} Ошибка создания платежа. Попробуйте позже.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        return

    await call.message.edit_text(
        f"<b>Оплата заказа #{order_id}</b>\n\n"
        f"Сумма: <b>{order.total_amount} ₽</b>\n"
        f"К оплате: <b>{payment.amount} USDT</b>",
        reply_markup=payment_link_kb(payment.pay_url, order_id, "crypto"),
        parse_mode="HTML",
    )


# ── ROLLYPAY (СБП) ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_rollypay_"))
async def cb_pay_rollypay(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    result = await session.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order.status != "pending":
        await call.answer("Заказ уже обработан", show_alert=True)
        return

    existing = await get_payment_by_order_provider(session, order_id, "rollypay")
    if existing and existing.pay_url:
        await call.message.edit_text(
            f"{CARD} <b>Оплата через СБП — заказ #{order_id}</b>\n\nСумма: <b>{order.total_amount} ₽</b>",
            reply_markup=payment_link_kb(existing.pay_url, order_id, "rollypay"),
            parse_mode="HTML",
        )
        await call.answer()
        return

    await call.answer("Создаю ссылку на оплату...")
    host = _get_webhook_host()
    payment = await create_rollypay_invoice(session, order, host, user_id=user.id)

    if not payment:
        await call.message.edit_text(
            f"{FAIL} Ошибка создания платежа RollyPay. Попробуйте другой способ оплаты.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        return

    await call.message.edit_text(
        f"{CARD} <b>Оплата через СБП</b>\n\n"
        f"Заказ: <b>#{order_id}</b>\n"
        f"Сумма: <b>{order.total_amount} ₽</b>\n\n"
        f"Нажмите кнопку ниже для перехода к оплате по СБП.",
        reply_markup=payment_link_kb(payment.pay_url, order_id, "rollypay"),
        parse_mode="HTML",
    )


# ── БАЛАНС ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_balance_"))
async def cb_pay_balance(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    result = await session.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order.status != "pending":
        await call.answer("Заказ уже обработан", show_alert=True)
        return

    db_user_result = await session.execute(select(User).where(User.id == user.id).with_for_update())
    db_user = db_user_result.scalar_one_or_none()
    if not db_user:
        await call.answer("Ошибка пользователя", show_alert=True)
        return

    if db_user.balance < order.total_amount:
        await call.answer(
            f"Недостаточно средств. Баланс: {db_user.balance:.2f} ₽, нужно: {order.total_amount} ₽",
            show_alert=True,
        )
        return

    db_user.balance -= order.total_amount
    order.status = "paid"

    payment_record = Payment(
        order_id=order.id,
        provider="balance",
        provider_invoice_id=f"balance_{order.id}_{int(datetime.now(timezone.utc).timestamp())}",
        amount=order.total_amount,
        currency="RUB",
        status="paid",
        pay_url=None,
        paid_at=datetime.now(timezone.utc),
    )
    session.add(payment_record)
    await session.commit()

    try:
        delivered = await deliver_order(session, order_id)
    except Exception as ex:
        from ..utils.helpers import logger as h_logger
        h_logger.error(f"deliver_order error after balance payment order#{order_id}: {ex}", exc_info=True)
        await call.message.edit_text(
            f"{OK} <b>Оплата прошла!</b>\n\n"
            f"{WARN} Произошла ошибка выдачи. Зайдите в <b>Мои заказы</b> и нажмите «Получить товар».",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer(f"{plain(OK)} Оплачено")
        return

    if not delivered:
        await call.message.edit_text(
            f"{OK} <b>Оплачено!</b>\n\n{WARN} Ошибка выдачи. Напишите в поддержку или зайдите в Мои заказы.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer(f"{plain(OK)} Оплата прошла")
        return

    items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
    await call.message.edit_text(
        f"{OK} <b>Оплачено с баланса!</b>\n\n{items_text}\n\nСохраните данные.",
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML",
    )
    await call.answer(f"{plain(OK)} Оплата прошла")


# ── ПРОВЕРКА ПЛАТЕЖА ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("check_payment_"))
async def cb_check_payment(call: CallbackQuery, session: AsyncSession, user: User):
    order_id, provider = _parse_check_payment(call.data)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    order = await get_order(session, order_id)
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return

    if order.status == "delivered":
        await call.answer(f"{plain(OK)} Заказ уже выдан", show_alert=True)
        return

    if order.status == "paid":
        delivered = await deliver_order(session, order_id)
        if not delivered:
            await call.answer("Ошибка выдачи товара. Напишите в поддержку.", show_alert=True)
            return
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
        await call.message.edit_text(
            f"{OK} <b>Оплачено!</b>\n\n{items_text}\n\nСохраните данные.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer(f"{plain(OK)} Оплата подтверждена")
        return

    if provider == "rollypay":
        await _check_rollypay(call, session, order_id, order)
    else:
        await _check_cryptobot(call, session, order_id, order)


async def _check_cryptobot(call, session, order_id, order):
    payment = await get_payment_for_check(session, order_id, "cryptobot")
    if not payment:
        payment = await get_payment_by_order(session, order_id)
    if not payment:
        await call.answer("Платёж не найден", show_alert=True)
        return

    if payment.status == "paid":
        delivered = await deliver_order(session, order_id)
        if not delivered:
            await call.answer("Ошибка выдачи. Напишите в поддержку.", show_alert=True)
            return
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
        await call.message.edit_text(
            f"{OK} <b>Оплачено!</b>\n\n{items_text}\n\nСохраните данные.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer(f"{plain(OK)} Оплата подтверждена")
        return

    status = await check_cryptobot_invoice(payment.provider_invoice_id)
    if status == "paid":
        locked = await session.execute(
            select(Payment).where(Payment.id == payment.id).with_for_update()
        )
        locked_payment = locked.scalar_one_or_none()
        if locked_payment is None:
            await call.answer("Платёж не найден. Напишите в поддержку.", show_alert=True)
            return
        if locked_payment.status == "paid":
            delivered = await deliver_order(session, order_id)
            if delivered:
                items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
                await call.message.edit_text(
                    f"{OK} <b>Оплачено!</b>\n\n{items_text}\n\nСохраните данные.",
                    reply_markup=back_to_menu_kb(),
                    parse_mode="HTML",
                )
            await call.answer(f"{plain(OK)} Оплата подтверждена")
            return
        await mark_payment_paid(session, locked_payment)
        delivered = await deliver_order(session, order_id)
        if not delivered:
            await call.answer("Ошибка выдачи. Напишите в поддержку.", show_alert=True)
            return
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
        await call.message.edit_text(
            f"{OK} <b>Оплачено!</b>\n\n{items_text}\n\nСохраните данные.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer(f"{plain(OK)} Оплата подтверждена")
    elif status == "expired":
        await call.answer("Время оплаты истекло. Создайте новый заказ.", show_alert=True)
    elif status == "active":
        await call.answer("Оплата ещё не поступила.", show_alert=True)
    else:
        await call.answer(f"Статус: {status}", show_alert=True)


async def _check_rollypay(call, session, order_id, order):
    from ..services.settings_service import get_cached
    from ..config import settings as env_settings

    api_key = get_cached("rollypay_api_key") or env_settings.rollypay_api_key
    if not api_key:
        await call.answer("RollyPay не настроен", show_alert=True)
        return

    payment = await get_payment_for_check(session, order_id, "rollypay")
    if not payment:
        await call.answer("Платёж не найден", show_alert=True)
        return

    if payment.status == "paid":
        delivered = await deliver_order(session, order_id)
        if not delivered:
            await call.answer("Ошибка выдачи. Напишите в поддержку.", show_alert=True)
            return
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
        await call.message.edit_text(
            f"{OK} <b>Оплачено через СБП!</b>\n\n{items_text}\n\nСохраните данные.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer(f"{plain(OK)} Оплата подтверждена")
        return

    status = await check_rollypay_payment(payment.provider_invoice_id, api_key)
    if status == "paid":
        locked = await session.execute(
            select(Payment).where(Payment.id == payment.id).with_for_update()
        )
        locked_payment = locked.scalar_one_or_none()
        if locked_payment is None:
            await call.answer("Платёж не найден. Напишите в поддержку.", show_alert=True)
            return
        if locked_payment.status == "paid":
            delivered = await deliver_order(session, order_id)
            if delivered:
                items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
                await call.message.edit_text(
                    f"{OK} <b>Оплачено через СБП!</b>\n\n{items_text}\n\nСохраните данные.",
                    reply_markup=back_to_menu_kb(),
                    parse_mode="HTML",
                )
            await call.answer(f"{plain(OK)} Оплата подтверждена")
            return
        await mark_payment_paid(session, locked_payment)
        delivered = await deliver_order(session, order_id)
        if not delivered:
            await call.answer("Ошибка выдачи. Напишите в поддержку.", show_alert=True)
            return
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
        await call.message.edit_text(
            f"{OK} <b>Оплачено через СБП!</b>\n\n{items_text}\n\nСохраните данные.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer(f"{plain(OK)} Оплата подтверждена")
    elif status == "created":
        await call.answer("Оплата ещё не поступила. Попробуйте позже.", show_alert=True)
    elif status == "failed":
        await call.answer("Платёж отклонён или истёк. Создайте новый заказ.", show_alert=True)
    else:
        await call.answer(f"Статус: {status}", show_alert=True)


# ── ОТМЕНА ЗАКАЗА ────────────────────────────────────────────────────────────

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
        await call.answer("Нельзя отменить этот заказ.", show_alert=True)
        return

    await cancel_order(session, order_id)
    await call.message.edit_text(
        f"{FAIL} <b>Заказ #{order_id} отменён.</b>",
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML",
    )
    await call.answer("Заказ отменён")
