from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...models import User, Admin
from ...keyboards.admin import admin_users_kb, admin_user_detail_kb, cancel_kb
from ...services.admin_service import (
    is_admin, get_users_paginated, toggle_user_ban, log_action, get_orders_paginated
)
from ...services.order_service import get_user_orders
from ...utils.emoji import (
    USERS, SHIELD, BANNED, OK, FAIL, BACK, STATS, ORDERS, PROFILE, plain
)

router = Router()


class UserSearchState(StatesGroup):
    waiting_user_id = State()


@router.callback_query(F.data == "admin_users")
async def cb_admin_users(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    users = await get_users_paginated(session, 0, 15)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for u in users:
        ban_icon = plain(BANNED) if u.is_banned else plain(SHIELD)
        name = u.first_name or f"id{u.id}"
        builder.row(InlineKeyboardButton(
            text=f"{ban_icon} {name} · {u.id}",
            callback_data=f"admin_user_{u.id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_main"))

    text = (
        f"{USERS} <b>Пользователи</b>\n"
        f"{'━' * 16}\n\n"
        f"Последние {len(users)} зарегистрированных:"
    )
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("admin_user_") & ~F.data.startswith("admin_user_orders_"))
async def cb_admin_user_detail(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    target_id = int(call.data.split("_")[2])
    result = await session.execute(select(User).where(User.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        return await call.answer("Пользователь не найден", show_alert=True)

    ban_status = f"{BANNED} Заблокирован" if target.is_banned else f"{SHIELD} Активен"
    text = (
        f"{PROFILE} <b>Пользователь #{target.id}</b>\n"
        f"{'━' * 16}\n\n"
        f"👤 Имя: {target.first_name or '—'}\n"
        f"📛 Username: @{target.username or '—'}\n"
        f"📌 Статус: {ban_status}\n"
        f"{'━' * 16}\n"
        f"{STATS} Потрачено: <b>{target.total_spent} руб.</b>\n"
        f"📅 Регистрация: {target.created_at.strftime('%d.%m.%Y')}"
    )
    await call.message.edit_text(
        text,
        reply_markup=admin_user_detail_kb(target.id, target.is_banned),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_ban_"))
async def cb_admin_ban(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    target_id = int(call.data.split("_")[2])
    new_banned = await toggle_user_ban(session, target_id)
    await log_action(session, user.id, "toggle_ban", "user", target_id, {"banned": new_banned})
    status = f"{plain(BANNED)} заблокирован" if new_banned else f"{plain(OK)} разблокирован"
    await call.answer(f"Пользователь {status}", show_alert=True)
    call.data = f"admin_user_{target_id}"
    await cb_admin_user_detail(call, session, user)


@router.callback_query(F.data.startswith("admin_user_orders_"))
async def cb_admin_user_orders(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    target_id = int(call.data.split("_")[3])
    orders = await get_user_orders(session, target_id, limit=20)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for order in orders:
        status_e = {
            "pending": "⏳", "paid": plain(OK), "delivered": plain(KEY), "cancelled": plain(FAIL)
        }.get(order.status, "❓")
        builder.row(InlineKeyboardButton(
            text=f"{status_e} #{order.id} — {order.total_amount}₽",
            callback_data=f"admin_order_{order.id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data=f"admin_user_{target_id}"))

    text = (
        f"{ORDERS} <b>Заказы пользователя {target_id}</b>\n"
        f"{'━' * 16}\n\n"
        f"Всего: <b>{len(orders)}</b>"
    )
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()
