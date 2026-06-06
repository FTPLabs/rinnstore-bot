from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from ...models import User
from ...keyboards.admin import admin_main_kb
from ...services.admin_service import is_admin, get_stats

router = Router()


def stats_text(stats: dict) -> str:
    return (
        f"<b>RINN STORE · Админ</b>\n\n"
        f"👥 {stats['total_users']} пользователей\n"
        f"📋 {stats['paid_orders']}/{stats['total_orders']} заказов оплачено\n"
        f"💰 {stats['total_revenue']} ₽ выручка\n"
        f"🔑 {stats['available_items']} ключей в наличии"
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    await state.clear()
    stats = await get_stats(session)
    await message.answer(stats_text(stats), reply_markup=admin_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "admin_main")
async def cb_admin_main(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    stats = await get_stats(session)
    await call.message.edit_text(stats_text(stats), reply_markup=admin_main_kb(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "admin_cancel_state")
async def cb_admin_cancel_state(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    stats = await get_stats(session)
    await call.message.edit_text(stats_text(stats), reply_markup=admin_main_kb(), parse_mode="HTML")
    await call.answer("Отменено")


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.clear()
    stats = await get_stats(session)
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    await call.message.edit_text(stats_text(stats), reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()
