import html
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Review, User, Order
from ..keyboards.review import comment_kb, rating_kb
from ..utils.i18n import t

router = Router()


class ReviewState(StatesGroup):
    waiting_comment = State()


def _product_names(order) -> str:
    return ", ".join(item.product.name for item in order.items if item.product) or "—"


async def _show_review_prompt(call: CallbackQuery, review: Review, user: User, session: AsyncSession):
    order = review.order or await session.get(Order, review.order_id)
    product = _product_names(order) if order else "—"
    amount = order.total_amount if order else "—"
    await call.message.answer(
        t(user, "review_prompt", product=html.escape(product), amount=amount, order_id=review.order_id),
        reply_markup=rating_kb(review.id), parse_mode="HTML",
    )


@router.callback_query(F.data.regexp(r"^review_order_\d+$"))
async def review_order(call: CallbackQuery, session: AsyncSession, user: User):
    order_id = int(call.data.rsplit("_", 1)[1])
    result = await session.execute(select(Review).where(Review.order_id == order_id))
    review = result.scalar_one_or_none()
    if not review or review.user_id != user.id:
        await call.answer(t(user, "review_unavailable"), show_alert=True)
        return
    if review.status != "awaiting_rating":
        await call.answer(t(user, "review_unavailable"), show_alert=True)
        return
    await _show_review_prompt(call, review, user, session)
    await call.answer()


@router.callback_query(F.data.regexp(r"^review_rate_\d+_[1-5]$"))
async def rate_review(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    parts = call.data.split("_")
    review_id, rating = int(parts[2]), int(parts[3])
    result = await session.execute(select(Review).where(Review.id == review_id).with_for_update())
    review = result.scalar_one_or_none()
    if not review or review.user_id != user.id or review.status != "awaiting_rating":
        await call.answer(t(user, "review_unavailable"), show_alert=True)
        return
    review.rating = rating
    review.status = "awaiting_comment"
    review.rated_at = datetime.now(timezone.utc)
    await session.commit()
    await state.set_state(ReviewState.waiting_comment)
    await state.update_data(review_id=review.id)
    await call.message.answer(t(user, "review_rate"), reply_markup=comment_kb(review.id))
    await call.answer()


async def _complete(session: AsyncSession, review: Review, comment: str | None = None):
    review.comment = comment[:2000] if comment else None
    review.status = "completed"
    review.completed_at = datetime.now(timezone.utc)
    await session.commit()


@router.callback_query(F.data.regexp(r"^review_skip_\d+$"))
async def skip_comment(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    review_id = int(call.data.split("_")[2])
    result = await session.execute(select(Review).where(Review.id == review_id).with_for_update())
    review = result.scalar_one_or_none()
    if not review or review.user_id != user.id or review.status != "awaiting_comment":
        await call.answer(t(user, "review_unavailable"), show_alert=True)
        return
    await _complete(session, review)
    await state.clear()
    await call.message.edit_text(t(user, "review_saved"), reply_markup=comment_kb(review.id))
    await call.answer()


@router.message(ReviewState.waiting_comment, F.text)
async def save_comment(message: Message, session: AsyncSession, user: User, state: FSMContext):
    data = await state.get_data()
    review_id = data.get("review_id")
    result = await session.execute(select(Review).where(Review.id == review_id).with_for_update())
    review = result.scalar_one_or_none()
    if not review or review.user_id != user.id or review.status != "awaiting_comment":
        await state.clear()
        await message.answer(t(user, "review_unavailable"))
        return
    await _complete(session, review, message.text.strip())
    await state.clear()
    await message.answer(t(user, "review_saved"), reply_markup=comment_kb(review.id))
