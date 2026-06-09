import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...models import User
from ...keyboards.admin import cancel_kb
from ...services.admin_service import is_admin, log_action
from ...utils.emoji import BROADCAST, OK, FAIL, STATS, WARN, plain

logger = logging.getLogger(__name__)
router = Router()

BATCH_SIZE = 25
BATCH_DELAY = 1.1
PROGRESS_EVERY = 50

_broadcast_running = False


class BroadcastState(StatesGroup):
    waiting_message = State()
    confirm = State()


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)

    if _broadcast_running:
        return await call.answer("⏳ Рассылка уже выполняется, подождите.", show_alert=True)

    await state.set_state(BroadcastState.waiting_message)
    await call.message.edit_text(
        f"{BROADCAST} <b>Рассылка</b>\n"
        f"{'━' * 16}\n\n"
        f"Отправьте сообщение для рассылки.\n"
        f"Поддерживается <b>HTML-разметка</b>.\n\n"
        f"Рассылка пойдёт <b>всем активным пользователям</b>.",
        reply_markup=cancel_kb(),
        parse_mode="HTML",
    )
    await call.answer()


@router.message(BroadcastState.waiting_message)
async def process_broadcast_text(message: Message, state: FSMContext):
    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer(f"{FAIL} Сообщение пустое. Введите текст:", reply_markup=cancel_kb(), parse_mode="HTML")
        return

    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastState.confirm)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{plain(OK)} Отправить всем", callback_data="confirm_broadcast"),
        InlineKeyboardButton(text=f"{plain(FAIL)} Отмена", callback_data="admin_main"),
    )
    preview = text[:300] + ("..." if len(text) > 300 else "")
    await message.answer(
        f"{BROADCAST} <b>Предпросмотр рассылки:</b>\n"
        f"{'━' * 16}\n\n"
        f"{preview}\n\n"
        f"{'━' * 16}\n\n"
        f"Отправить?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "confirm_broadcast", BroadcastState.confirm)
async def process_confirm_broadcast(
    call: CallbackQuery, session: AsyncSession, user: User,
    state: FSMContext, bot: Bot,
):
    global _broadcast_running

    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)

    if _broadcast_running:
        return await call.answer("⏳ Рассылка уже выполняется.", show_alert=True)

    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()

    result = await session.execute(select(User.id).where(User.is_banned == False))
    user_ids = result.scalars().all()
    total = len(user_ids)

    _broadcast_running = True
    status_msg = await call.message.edit_text(
        f"{BROADCAST} <b>Рассылка запущена</b>\n\n"
        f"Получателей: <b>{total}</b>\n"
        f"Прогресс: <b>0 / {total}</b>",
        parse_mode="HTML",
    )

    sent = 0
    failed = 0
    try:
        for i, uid in enumerate(user_ids):
            try:
                await bot.send_message(uid, text, parse_mode="HTML")
                sent += 1
            except Exception as ex:
                failed += 1
                logger.debug(f"Broadcast: не удалось отправить {uid}: {ex}")

            if (i + 1) % BATCH_SIZE == 0:
                await asyncio.sleep(BATCH_DELAY)

            if (i + 1) % PROGRESS_EVERY == 0:
                try:
                    await status_msg.edit_text(
                        f"{BROADCAST} <b>Рассылка...</b>\n\n"
                        f"Прогресс: <b>{i + 1} / {total}</b>\n"
                        f"{OK} Доставлено: <b>{sent}</b> · {FAIL} Ошибок: <b>{failed}</b>",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
    finally:
        _broadcast_running = False

    await log_action(session, user.id, "broadcast", details={"sent": sent, "failed": failed, "total": total})

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{plain(BROADCAST)} В меню", callback_data="admin_main"))
    await status_msg.edit_text(
        f"{OK} <b>Рассылка завершена</b>\n"
        f"{'━' * 16}\n\n"
        f"{STATS} Всего: <b>{total}</b>\n"
        f"{OK} Доставлено: <b>{sent}</b>\n"
        f"{FAIL} Не доставлено: <b>{failed}</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
