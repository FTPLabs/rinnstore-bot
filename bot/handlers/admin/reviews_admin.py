import html
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ...models import Review, Order, User
from ...services.admin_service import is_admin, log_action
from ...services.review_service import format_review_text, BUY_URL
from ...services.settings_service import get_cached
from ...utils.emoji import OK, FAIL

router = Router()


def buy_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛒 Купить свой ключ", url=BUY_URL, style="primary")
    ]])


async def _get_review(session: AsyncSession, review_id: int):
    result = await session.execute(
        select(Review).options(selectinload(Review.order).selectinload(Order.items)).where(Review.id == review_id)
    )
    return result.scalar_one_or_none()


@router.callback_query(F.data.regexp(r"^review_approve_\d+$"))
async def approve_review(call: CallbackQuery, session: AsyncSession, user: User, bot: Bot):
    if not await is_admin(session, user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    review_id = int(call.data.rsplit("_", 1)[1])
    review = await _get_review(session, review_id)
    channel = (get_cached("review_channel_id") or "").strip()
    if not review or review.status != "completed" or review.moderation_status not in ("pending", "notified"):
        await call.answer("Отзыв уже обработан", show_alert=True)
        return
    if not channel:
        await call.answer("Канал отзывов не настроен", show_alert=True)
        return
    buyer = await session.get(User, review.user_id)
    me = await bot.get_me()
    text = format_review_text(review, review.order, buyer, me.username or "rinnnstore_bot")
    sent = await bot.send_message(channel, text, reply_markup=buy_kb(), parse_mode="HTML")
    review.moderation_status = "approved"
    review.publication_status = "published"
    review.published_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    review.channel_message_id = sent.message_id
    await log_action(session, user.id, "approve_review", "review", review.id, {"channel_message_id": sent.message_id})
    await session.commit()
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"{OK} Отзыв одобрен и опубликован в канале.", parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.regexp(r"^review_reject_\d+$"))
async def reject_review(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    review_id = int(call.data.rsplit("_", 1)[1])
    review = await _get_review(session, review_id)
    if not review or review.status != "completed" or review.moderation_status not in ("pending", "notified"):
        await call.answer("Отзыв уже обработан", show_alert=True)
        return
    review.moderation_status = "rejected"
    review.publication_status = "rejected"
    await log_action(session, user.id, "reject_review", "review", review.id)
    await session.commit()
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"{FAIL} Отзыв отклонён.", parse_mode="HTML")
    await call.answer()
