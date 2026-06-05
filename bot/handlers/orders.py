from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import User
from ..keyboards.user import orders_kb, order_detail_kb, back_to_menu_kb
from ..services.order_service import get_user_orders, get_order, deliver_order
from ..utils.helpers import parse_callback_int
from ..utils.emoji import KEY, OK, FAIL

router = Router()

STATUS_MAP = {
    "pending": "⏳ Ожидает оплаты",
    "paid": "✅ Оплачен",
    "delivered": "🔑 Выдан",
    "cancelled": "✕ Отменён",
    "partial": "⚠️ Частично выдан",
}


@router.callback_query(F.data == "my_orders")
async def cb_my_orders(call: CallbackQuery, session: AsyncSession, user: User):
    orders = await get_user_orders(session, user.id)
    if not orders:
        await call.message.edit_text("Заказов пока нет.", reply_markup=back_to_menu_kb())
        await call.answer()
        return

    await call.message.edit_text(
        "<b>Мои заказы</b>",
        reply_markup=orders_kb(orders),
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^order_\d+$"))
async def cb_order_detail(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 1)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    order = await get_order(session, order_id)
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return

    status_text = STATUS_MAP.get(order.status, order.status)
    items_text = "\n".join(
        f"{item.product.name} × {item.quantity} — {float(item.unit_price) * item.quantity:.0f} ₽"
        for item in order.items
    )

    text = (
        f"<b>Заказ #{order.id}</b>\n"
        f"{order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"{items_text}\n\n"
        f"Итого: <b>{order.total_amount} ₽</b>\n"
        f"Статус: {status_text}"
    )
    await call.message.edit_text(text, reply_markup=order_detail_kb(order_id, order.status))
    await call.answer()


@router.callback_query(F.data.startswith("get_items_"))
async def cb_get_items(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    order = await get_order(session, order_id)
    if not order or order.user_id != user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order.status not in ("paid", "delivered"):
        await call.answer("Заказ ещё не оплачен", show_alert=True)
        return

    delivered = await deliver_order(session, order_id)
    if not delivered:
        await call.answer("Ошибка выдачи. Напишите в поддержку.", show_alert=True)
        return

    items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
    await call.message.edit_text(
        f"{OK} <b>Товары заказа #{order_id}</b>\n\n{items_text}",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()
