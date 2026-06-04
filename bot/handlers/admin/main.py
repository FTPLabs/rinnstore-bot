from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from ...models import User
from ...keyboards.admin import admin_main_kb
from ...services.admin_service import is_admin, get_stats

router = Router()


async def require_admin(call_or_msg, session: AsyncSession, user: User) -> bool:
    if not await is_admin(session, user.id):
        if hasattr(call_or_msg, "answer"):
            await call_or_msg.answer("🚫 Нет доступа.")
        return False
    return True


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        await message.answer("🚫 У вас нет доступа к админ-панели.")
        return
    stats = await get_stats(session)
    text = (
        f"🔧 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"📋 Заказов всего: <b>{stats['total_orders']}</b>\n"
        f"✅ Оплаченных: <b>{stats['paid_orders']}</b>\n"
        f"💰 Выручка: <b>{stats['total_revenue']} руб.</b>\n"
        f"📦 Товаров: <b>{stats['total_products']}</b>\n"
        f"🔑 Ключей в наличии: <b>{stats['available_items']}</b>"
    )
    await message.answer(text, reply_markup=admin_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "admin_main")
async def cb_admin_main(call: CallbackQuery, session: AsyncSession, user: User):
    if not await require_admin(call, session, user):
        return
    stats = await get_stats(session)
    text = (
        f"🔧 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"📋 Заказов: <b>{stats['total_orders']}</b>\n"
        f"✅ Оплаченных: <b>{stats['paid_orders']}</b>\n"
        f"💰 Выручка: <b>{stats['total_revenue']} руб.</b>\n"
        f"📦 Товаров: <b>{stats['total_products']}</b>\n"
        f"🔑 Ключей в наличии: <b>{stats['available_items']}</b>"
    )
    await call.message.edit_text(text, reply_markup=admin_main_kb(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery, session: AsyncSession, user: User):
    if not await require_admin(call, session, user):
        return
    stats = await get_stats(session)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main"))
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"📋 Заказов всего: <b>{stats['total_orders']}</b>\n"
        f"✅ Оплаченных заказов: <b>{stats['paid_orders']}</b>\n"
        f"💰 Общая выручка: <b>{stats['total_revenue']} руб.</b>\n"
        f"📦 Активных товаров: <b>{stats['total_products']}</b>\n"
        f"🔑 Доступных ключей: <b>{stats['available_items']}</b>\n"
    )
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()
