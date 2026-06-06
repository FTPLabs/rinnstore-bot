from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import User
from ..keyboards.user import back_to_menu_kb
from ..services.order_service import get_order, deliver_order, cancel_order
from ..utils.helpers import parse_callback_int
from ..utils.emoji import KEY, OK, FAIL

router = Router()


@router.callback_query(F.data == "cart")
async def cb_cart(call: CallbackQuery):
    from ..keyboards.user import catalog_kb as _
    await call.message.edit_text(
        "🛍 Корзина не используется. Покупка происходит сразу из карточки товара.",
        reply_markup=back_to_menu_kb()
    )
    await call.answer()


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
