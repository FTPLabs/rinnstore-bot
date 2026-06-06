import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...models import User
from ...keyboards.admin import cancel_kb
from ...services.admin_service import is_admin, log_action
from ...utils.emoji import BROADCAST, OK, FAIL, STATS, plain

router = Router()

BATCH_SIZE = 25
BATCH_DELAY = 1.1


class BroadcastState(StatesGroup):
    waiting_message = State()
    confirm = State()


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.set_state(BroadcastState.waiting_message)
    await call.message.edit_text(
        f"{BROADCAST} <b>Рассылка</b>\n"
        f"{'━' * 16}\n\n"
        f"Введите текст сообщения.\nПоддерживается HTML-разметка.\n\n"
        f"Рассылка будет отправлена <b>всем пользователям</b>.",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(BroadcastState.waiting_message)
async def process_broadcast_text(message: Message, state: FSMContext):
    text = message.text or message.caption or ""
    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastState.confirm)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{plain(OK)} Отправить всем", callback_data="confirm_broadcast"),
        InlineKeyboardButton(text=f"{plain(FAIL)} Отмена", callback_data="admin_main"),
    )
    await message.answer(
        f"{BROADCAST} <b>Предпросмотр рассылки:</b>\n"
        f"{'━' * 16}\n\n"
        f"{text}\n\n"
        f"{'━' * 16}\n\n"
        f"Отправить?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "confirm_broadcast", BroadcastState.confirm)
async def process_confirm_broadcast(
    call: CallbackQuery, session: AsyncSession, user: User,
    state: FSMContext, bot: Bot
):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()

    result = await session.execute(
        select(User.id).where(User.is_banned == False)
    )
    user_ids = result.scalars().all()

    await call.message.edit_text(
        f"{BROADCAST} Рассылка запущена для <b>{len(user_ids)}</b> пользователей...",
        parse_mode="HTML"
    )

    sent = 0
    failed = 0
    for i, uid in enumerate(user_ids):
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

        if (i + 1) % BATCH_SIZE == 0:
            await asyncio.sleep(BATCH_DELAY)

    await log_action(session, user.id, "broadcast", details={"sent": sent, "failed": failed})
    await call.message.edit_text(
        f"{OK} <b>Рассылка завершена</b>\n\n"
        f"{STATS} Отправлено: <b>{sent}</b>\n"
        f"{FAIL} Ошибок: <b>{failed}</b>",
        parse_mode="HTML"
    )
