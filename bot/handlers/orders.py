from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import User
from ..keyboards.user import orders_kb, order_detail_kb, back_to_menu_kb
from ..services.order_service import get_user_orders, get_order, deliver_order
from ..utils.emoji import (
    BAG, KEY, OK, FAIL, BACK, CLOCK, STAR, ORDERS, TAG
)

router = Router()

STATUS_MAP = {
    "pending": f"{CLOCK} Ожидает оплаты",
    "paid": f"{OK} Оплачен",
    "delivered": f"{KEY} Выдан",
    "cancelled": f"{FAIL} Отменён",
}


@router.callback_query(F.data == "my_orders")
async def cb_my_orders(call: CallbackQuery, session: AsyncSession, user: User):
    orders = await get_user_orders(session, user.id)

    if not orders:
        await call.message.edit_text(
            f"{ORDERS} <b>Мои заказы</b>\n\n"
            f"У вас пока нет заказов.\n"
            f"Перейдите в каталог и сделайте первую покупку!",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer()
        return

    await call.message.edit_text(
        f"{ORDERS} <b>Мои заказы</b>\n"
        f"{'━' * 16}\n\n"
        f"Выберите заказ для просмотра:",
        reply_markup=orders_kb(orders),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^order_\d+$"))
async def cb_order_detail(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = int(call.data.split("_")[1])
    order = await get_order(session, order_id)

    if not order or order.user_id != user.id:
        await call.answer("❌ Заказ не найден", show_alert=True)
        return

    status_text = STATUS_MAP.get(order.status, order.status)
    items_text = "\n".join(
        f"{TAG} {item.product.name} × {item.quantity} = {float(item.unit_price) * item.quantity:.2f} руб."
        for item in order.items
    )

    text = (
        f"{BAG} <b>Заказ #{order.id}</b>\n"
        f"{'━' * 16}\n\n"
        f"📅 {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"📌 {status_text}\n"
        f"{'━' * 16}\n"
        f"{items_text}\n"
        f"{'━' * 16}\n"
        f"💰 Итого: <b>{order.total_amount} руб.</b>"
    )

    await call.message.edit_text(
        text,
        reply_markup=order_detail_kb(order_id, order.status),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.startswith("get_items_"))
async def cb_get_items(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = int(call.data.split("_")[2])
    order = await get_order(session, order_id)

    if not order or order.user_id != user.id:
        await call.answer("❌ Заказ не найден", show_alert=True)
        return

    if order.status not in ("paid", "delivered"):
        await call.answer("⚠️ Заказ ещё не оплачен", show_alert=True)
        return

    delivered = await deliver_order(session, order_id)
    if not delivered:
        await call.answer("❌ Ошибка выдачи. Обратитесь в поддержку.", show_alert=True)
        return

    items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
    await call.message.edit_text(
        f"{OK} <b>Товары по заказу #{order_id}</b>\n"
        f"{'━' * 16}\n\n"
        f"{items_text}\n\n"
        f"{STAR} Сохраните данные в надёжном месте!",
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML",
    )
    await call.answer()
