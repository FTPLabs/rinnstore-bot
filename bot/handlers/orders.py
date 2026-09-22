from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import User
from ..keyboards.user import orders_kb, order_detail_kb, back_to_menu_kb
from ..services.order_service import get_user_orders, get_order, deliver_order
from ..utils.helpers import parse_callback_int
from ..utils.emoji import KEY, OK, FAIL, WARN, CLOCK, plain
from ..utils.i18n import t

router = Router()


def status_text(status: str, user) -> str:
    return {
        "pending": f"{plain(CLOCK)} {t(user, 'pending')}",
        "paid": f"{plain(OK)} {t(user, 'paid')}",
        "delivered": f"{plain(KEY)} {t(user, 'delivered')}",
        "cancelled": f"{plain(FAIL)} {t(user, 'cancelled')}",
        "partial": f"{plain(WARN)} {t(user, 'partial')}",
    }.get(status, status)


@router.callback_query(F.data == "my_orders")
async def cb_my_orders(call: CallbackQuery, session: AsyncSession, user: User):
    orders = await get_user_orders(session, user.id)
    if not orders:
        await call.message.edit_text(t(user, "orders_empty"), reply_markup=back_to_menu_kb(user.language_code))
        await call.answer()
        return
    await call.message.edit_text(
        f"<b>{t(user, 'my_orders')}</b>",
        reply_markup=orders_kb(orders, language=user.language_code),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^order_\d+$"))
async def cb_order_detail(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 1)
    if order_id is None:
        await call.answer(t(user, "error_data"), show_alert=True)
        return
    order = await get_order(session, order_id)
    if not order or order.user_id != user.id:
        await call.answer(t(user, "order_not_found"), show_alert=True)
        return
    items_text = "\n".join(
        f"{item.product.name} × {item.quantity} — {float(item.unit_price) * item.quantity:.0f} ₽"
        for item in order.items
    )
    text = (
        f"<b>{t(user, 'order')} #{order.id}</b>\n"
        f"{order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"{items_text}\n\n"
        f"{t(user, 'total')}: <b>{order.total_amount} ₽</b>\n"
        f"{t(user, 'status')}: {status_text(order.status, user)}"
    )
    await call.message.edit_text(
        text,
        reply_markup=order_detail_kb(order_id, order.status, user.language_code),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.startswith("get_items_"))
async def cb_get_items(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = parse_callback_int(call.data, 2)
    if order_id is None:
        await call.answer(t(user, "error_data"), show_alert=True)
        return
    order = await get_order(session, order_id)
    if not order or order.user_id != user.id:
        await call.answer(t(user, "order_not_found"), show_alert=True)
        return
    if order.status not in ("paid", "delivered", "partial"):
        await call.answer(t(user, "not_paid"), show_alert=True)
        return
    delivered = await deliver_order(session, order_id)
    if not delivered:
        await call.answer(t(user, "data_delivery_error"), show_alert=True)
        return
    items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
    await call.message.edit_text(
        f"{OK} <b>{t(user, 'delivered_items')} #{order_id}</b>\n\n{items_text}",
        reply_markup=back_to_menu_kb(user.language_code),
        parse_mode="HTML",
    )
    await call.answer()


__all__ = ["router"]
