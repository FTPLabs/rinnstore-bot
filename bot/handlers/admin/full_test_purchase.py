"""Admin-only one-click end-to-end purchase simulation."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...keyboards.review import rating_kb
from ...models import Payment, Product, ProductItem, Review, User
from ...services.admin_service import is_admin, log_action
from ...services.order_service import (
    create_order,
    create_review_after_delivery_notification,
    deliver_order,
)
from ...utils.delivery import format_delivered_items
from ...utils.emoji import FAIL, KEY, OK

router = Router()
TEST_PRICE = Decimal("1.00")
TEST_PROVIDER = "test_simulation"
TEST_NOTE = "admin_full_test_purchase_fake_product"


def _cancel_kb() -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✕ Закрыть", callback_data="admin_main"))
    return builder.as_markup()


async def _create_and_sell_fake_product(session: AsyncSession, admin_id: int):
    token = uuid4().hex[:10].upper()
    product = Product(
        category_id=None,
        name=f"Тестовый товар {token}",
        description="Служебный товар для проверки полной покупки",
        price=TEST_PRICE,
        currency="RUB",
        is_active=False,
        is_unlimited=False,
    )
    session.add(product)
    await session.flush()
    item = ProductItem(
        product_id=product.id,
        data=f"TEST-KEY-{token}",
        is_sold=False,
        is_reserved=False,
    )
    session.add(item)
    await session.flush()

    order = await create_order(session, admin_id, [{
        "product_id": product.id,
        "qty": 1,
        "price": TEST_PRICE,
    }])
    order.notes = TEST_NOTE
    payment = Payment(
        order_id=order.id,
        provider=TEST_PROVIDER,
        provider_invoice_id=f"test_{order.id}_{token}",
        amount=order.total_amount,
        currency="RUB",
        status="paid",
        pay_url=None,
        payload={"test": True, "fake_product": True},
        paid_at=datetime.now(timezone.utc),
    )
    session.add(payment)
    order.status = "paid"
    await session.commit()

    delivered = await deliver_order(session, order.id)
    if not delivered or any(row.get("product_item_id") is None for row in delivered):
        return product, order, delivered, None

    await create_review_after_delivery_notification(session, order.id)
    review = (await session.execute(
        select(Review).where(Review.order_id == order.id)
    )).scalar_one_or_none()
    return product, order, delivered, review


@router.callback_query(F.data == "admin_full_test_purchase")
async def cb_full_test_purchase(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)

    product, order, delivered, review = await _create_and_sell_fake_product(session, user.id)
    if not delivered or any(row.get("product_item_id") is None for row in delivered):
        await call.message.edit_text(
            f"{FAIL} Не удалось завершить фейковую покупку. Заказ: <code>#{order.id}</code>",
            reply_markup=_cancel_kb(), parse_mode="HTML",
        )
        await call.answer("Ошибка тестовой выдачи", show_alert=True)
        return

    items_text = format_delivered_items(delivered)
    text = (
        f"{OK} <b>Полная тестовая покупка завершена</b>\n\n"
        f"Фейковый товар: <b>{product.name}</b>\n"
        f"Сумма: <b>{order.total_amount} ₽</b>\n"
        f"Заказ: <code>#{order.id}</code>\n"
        "Платёж: <b>имитация, без списания денег</b>\n\n"
        f"{KEY} <b>Выданный тестовый ключ:</b>\n{items_text}\n\n"
        "Товар скрыт от покупателей и создан только для этой проверки. "
        "Ниже запущен обычный сценарий отзыва."
    )
    await call.message.edit_text(text, reply_markup=_cancel_kb(), parse_mode="HTML")
    if review:
        await call.message.answer(
            f"<b>Тестовый отзыв по заказу #{order.id}</b>\n\nОцените полученный товар:",
            reply_markup=rating_kb(review.id), parse_mode="HTML",
        )
    await log_action(session, user.id, "full_test_purchase_fake_product", "order", order.id, {
        "product_id": product.id,
        "review_id": review.id if review else None,
        "fake_product": True,
    })
    await call.answer("Тестовая покупка завершена")
