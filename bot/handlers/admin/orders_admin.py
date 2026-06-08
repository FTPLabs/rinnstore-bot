from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...models import User, Order
from ...keyboards.admin import admin_orders_kb, admin_order_detail_kb
from ...services.admin_service import is_admin, get_orders_paginated, log_action
from ...services.order_service import deliver_order, cancel_order, get_order
from ...utils.helpers import parse_callback_int
from ...utils.emoji import (
    ORDERS, KEY, OK, FAIL, BACK, CLOCK, STATS, BAG, TAG, plain
)

router = Router()


PAGE_SIZE = 10
STATUS_MAP = {
    "pending": f"{CLOCK} Ожидает",
    "paid": f"{OK} Оплачен",
    "delivered": f"{KEY} Выдан",
    "cancelled": f"{FAIL} Отменён",
    "partial": "⚠️ Частично выдан",
}


@router.callback_query(F.data == "admin_orders")
async def cb_admin_orders(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    orders = await get_orders_paginated(session, 0, PAGE_SIZE)
    text = (
        f"{ORDERS} <b>Заказы</b>\n"
        f"{'━' * 16}\n\n"
        f"Последние {len(orders)} заказов:"
    )
    await call.message.edit_text(text, reply_markup=admin_orders_kb(orders, 0), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("admin_orders_page_"))
async def cb_admin_orders_page(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    page = parse_callback_int(call.data, 3)
    if page is None:
        return await call.answer("Ошибка данных", show_alert=True)
    orders = await get_orders_paginated(session, page * PAGE_SIZE, PAGE_SIZE)
    if not orders and page > 0:
        await call.answer("Больше заказов нет", show_alert=True)
        return
    await call.message.edit_text(
        f"{ORDERS} <b>Заказы — стр. {page+1}</b>",
        reply_markup=admin_orders_kb(orders, page),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_order_"))
async def cb_admin_order_detail(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    order = await get_order(session, order_id)
    if not order:
        return await call.answer("Заказ не найден", show_alert=True)

    status_text = STATUS_MAP.get(order.status, order.status)
    items_text = "\n".join(
        f"{TAG} {item.product.name} × {item.quantity} = {float(item.unit_price) * item.quantity:.2f}₽"
        for item in order.items
    )

    delivered_text = ""
    if order.delivered_items:
        delivered_keys = "\n".join(
            f"{KEY} <code>{di.product_item.data}</code>" if di.product_item else ""
            for di in order.delivered_items
        )
        delivered_text = f"\n\n{OK} <b>Выданные товары:</b>\n{delivered_keys}"

    text = (
        f"{BAG} <b>Заказ #{order.id}</b>\n"
        f"{'━' * 16}\n\n"
        f"👤 User ID: <code>{order.user_id}</code>\n"
        f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"📌 {status_text}\n"
        f"{'━' * 16}\n"
        f"{items_text}\n"
        f"{'━' * 16}\n"
        f"💰 Итого: <b>{order.total_amount} руб.</b>"
        f"{delivered_text}"
    )
    await call.message.edit_text(
        text,
        reply_markup=admin_order_detail_kb(order_id, order.status),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_deliver_"))
async def cb_admin_deliver(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    delivered = await deliver_order(session, order_id)
    await log_action(session, user.id, "manual_deliver", "order", order_id)
    await call.answer(f"✅ Выдано {len(delivered)} товаров", show_alert=True)
    call.data = f"admin_order_{order_id}"
    await cb_admin_order_detail(call, session, user)


@router.callback_query(F.data.startswith("admin_cancel_order_"))
async def cb_admin_cancel_order(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    order_id = parse_callback_int(call.data, 3)
    if order_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    await cancel_order(session, order_id)
    await log_action(session, user.id, "cancel_order", "order", order_id)
    await call.answer(f"❌ Заказ #{order_id} отменён", show_alert=True)
    await cb_admin_orders(call, session, user)
