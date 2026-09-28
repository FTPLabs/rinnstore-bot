"""Admin-only end-to-end purchase simulation.

The payment is always simulated locally; no provider API or real charge is made.
Product fulfilment uses the normal delivery path and therefore consumes a real
stock key (or creates an unlimited-product delivery copy), then creates the
normal review request for the admin user.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Payment, Product, ProductItem, Review, User
from ...services.admin_service import is_admin, log_action
from ...services.order_service import (
    create_order,
    create_review_after_delivery_notification,
    deliver_order,
)
from ...utils.delivery import format_delivered_items
from ...utils.emoji import FAIL, KEY, OK, plain
from ...keyboards.review import rating_kb

router = Router()
TEST_NOTE = "admin_full_test_purchase"
PROVIDERS: tuple[tuple[str, str], ...] = (
    ("freekassa", "FreeKassa"),
    ("cryptobot", "CryptoBot"),
    ("rollypay", "RollyPay / СБП"),
    ("telegram_stars", "Telegram Stars"),
    ("balance", "Баланс"),
    ("manual", "Ручная оплата"),
)


def _cancel_kb() -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_main"))
    return builder.as_markup()


def _products_kb(products: list[Product]) -> object:
    builder = InlineKeyboardBuilder()
    for product in products[:50]:
        builder.row(InlineKeyboardButton(
            text=f"{product.name} — {product.price} ₽",
            callback_data=f"admin_full_test_product_{product.id}",
        ))
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_main"))
    return builder.as_markup()


def _providers_kb(product_id: int) -> object:
    builder = InlineKeyboardBuilder()
    for provider, label in PROVIDERS:
        builder.row(InlineKeyboardButton(
            text=f"{label} (тест)",
            callback_data=f"admin_full_test_pay_{provider}_{product_id}",
            style="primary",
        ))
    builder.row(InlineKeyboardButton(text="Назад к товарам", callback_data="admin_full_test_purchase"))
    return builder.as_markup()


def _provider_label(provider: str) -> str:
    return dict(PROVIDERS).get(provider, provider)


@router.callback_query(F.data == "admin_full_test_purchase")
async def cb_full_test_purchase(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    result = await session.execute(
        select(Product).where(Product.is_active == True).order_by(Product.sort_order, Product.name)
    )
    products = result.scalars().all()
    if not products:
        await call.message.edit_text(f"{FAIL} Нет активных товаров.", reply_markup=_cancel_kb(), parse_mode="HTML")
        return await call.answer()
    await call.message.edit_text(
        "<b>Полная тестовая покупка</b>\n\n"
        "Выберите реальный товар. После симуляции ключ будет выдан обычным механизмом "
        "и списан со склада. Списание необратимо без восстановления backup.",
        reply_markup=_products_kb(products), parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^admin_full_test_product_\d+$"))
async def cb_full_test_product(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    product_id = int(call.data.rsplit("_", 1)[1])
    product = await session.get(Product, product_id)
    if not product or not product.is_active:
        return await call.answer("Товар недоступен", show_alert=True)
    await call.message.edit_text(
        f"<b>Тестовая покупка</b>\n\n"
        f"Товар: <b>{product.name}</b>\n"
        f"Сумма: <b>{product.price} ₽</b>\n\n"
        "Выберите платёжную систему для имитации. Реальное списание не выполняется:",
        reply_markup=_providers_kb(product.id), parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^admin_full_test_pay_[a-z_]+_\d+$"))
async def cb_full_test_pay(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    parts = call.data.split("_")
    try:
        product_id = int(parts[-1])
    except ValueError:
        return await call.answer("Ошибка данных", show_alert=True)
    provider = "_".join(parts[4:-1])
    if provider not in dict(PROVIDERS):
        return await call.answer("Неизвестная платёжная система", show_alert=True)
    product = await session.get(Product, product_id)
    if not product or not product.is_active:
        return await call.answer("Товар недоступен", show_alert=True)

    available = await session.execute(select(ProductItem.id).where(
        ProductItem.product_id == product_id,
        ProductItem.is_sold == False,
        ProductItem.is_reserved == False,
    ).limit(1))
    if available.scalar_one_or_none() is None and not product.is_unlimited:
        return await call.answer("У товара нет доступного ключа", show_alert=True)

    order = await create_order(session, user.id, [{
        "product_id": product.id,
        "qty": 1,
        "price": Decimal(str(product.price)),
    }])
    order.notes = TEST_NOTE
    payment = Payment(
        order_id=order.id,
        provider=provider,
        provider_invoice_id=f"test_{provider}_{order.id}",
        amount=order.total_amount,
        currency="RUB",
        status="paid",
        pay_url=None,
        payload={"test": True, "provider": provider},
        paid_at=datetime.now(timezone.utc),
    )
    session.add(payment)
    order.status = "paid"
    await session.commit()

    delivered = await deliver_order(session, order.id)
    if not delivered or any(item.get("product_item_id") is None for item in delivered):
        await call.message.edit_text(
            f"{FAIL} Оплата имитирована, но выдача не завершилась. Заказ: <code>#{order.id}</code>",
            reply_markup=_cancel_kb(), parse_mode="HTML",
        )
        await call.answer("Ошибка выдачи", show_alert=True)
        return

    await create_review_after_delivery_notification(session, order.id)
    review = (await session.execute(select(Review).where(Review.order_id == order.id))).scalar_one_or_none()
    items_text = format_delivered_items(delivered)
    text = (
        f"{OK} <b>Полная тестовая покупка завершена</b>\n\n"
        f"Заказ: <code>#{order.id}</code>\n"
        f"Товар: <b>{product.name}</b>\n"
        f"Платёжная система: <b>{_provider_label(provider)}</b> (имитация)\n"
        f"Оплачено: <b>{order.total_amount} ₽</b>\n\n"
        f"{KEY} <b>Реально выданный ключ:</b>\n{items_text}\n\n"
        "Запрос отзыва отправлен ниже. Пройдите оценку, анонимность и комментарий обычным сценарием."
    )
    await call.message.edit_text(text, reply_markup=_cancel_kb(), parse_mode="HTML")
    if review:
        await call.message.answer(
            f"<b>Тестовый отзыв по заказу #{order.id}</b>\n\nОцените полученный товар:",
            reply_markup=rating_kb(review.id), parse_mode="HTML",
        )
    await log_action(session, user.id, "full_test_purchase", "order", order.id, {
        "provider": provider, "product_id": product.id, "real_delivery": True,
        "review_id": review.id if review else None,
    })
    await call.answer("Тестовая покупка завершена")
