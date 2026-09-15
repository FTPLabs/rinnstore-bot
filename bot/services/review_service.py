import asyncio
import html
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ..database import AsyncSessionFactory
from ..models import Review, Order
from ..services.settings_service import get_cached
from ..keyboards.review import rating_kb
from ..utils.i18n import t

logger = logging.getLogger(__name__)


def _int_setting(key: str, default: int) -> int:
    try:
        return max(0, int(get_cached(key) or default))
    except (TypeError, ValueError):
        return default


async def review_worker(bot: Bot) -> None:
    logger.info("Review worker started")
    while True:
        try:
            await process_review_jobs(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Review worker error")
        await asyncio.sleep(60)


async def process_review_jobs(bot: Bot) -> None:
    if get_cached("reviews_enabled").lower() not in ("1", "true", "yes", "on"):
        return
    now = datetime.now(timezone.utc)
    initial = _int_setting("review_initial_delay_minutes", 1)
    interval = _int_setting("review_reminder_interval_hours", 24)
    max_reminders = _int_setting("review_max_reminders", 3)
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Review).options(
                selectinload(Review.order).selectinload(Order.items)
            ).where(
                Review.status == "awaiting_rating",
                Review.next_reminder_at <= now,
                Review.reminders_sent < max_reminders,
            ).order_by(Review.next_reminder_at).limit(50).with_for_update(skip_locked=True)
        )
        reviews = result.scalars().all()
        for review in reviews:
            try:
                product_names = ", ".join(item.product.name for item in (review.order.items if review.order else []) if item.product) or "—"
                await bot.send_message(
                    review.user_id,
                    t(review.order.user if review.order else "ru", "review_prompt", product=product_names, amount=review.order.total_amount if review.order else "—", order_id=review.order_id),
                    reply_markup=rating_kb(review.id),
                )
                review.reminders_sent += 1
                review.next_reminder_at = now + timedelta(hours=interval)
            except Exception as exc:
                review.last_error = str(exc)[:500]
                review.next_reminder_at = now + timedelta(minutes=10)
                logger.warning("Review prompt failed id=%s: %s", review.id, exc)
        await session.commit()

        result = await session.execute(
            select(Review).options(
                selectinload(Review.order).selectinload(Order.items)
            ).where(
                Review.status == "completed",
                Review.publication_status == "pending",
            ).order_by(Review.completed_at).limit(50).with_for_update(skip_locked=True)
        )
        completed = result.scalars().all()
        channel = get_cached("review_channel_id").strip()
        if channel:
            for review in completed:
                try:
                    comment = html.escape(review.comment or "Комментарий не оставлен")
                    text = (
                        f"⭐ <b>Новый отзыв о заказе #{review.order_id}</b>\n"
                        f"Оценка: <b>{review.rating}/5</b>\n"
                        f"Комментарий: {comment}"
                    )
                    sent = await bot.send_message(channel, text, parse_mode="HTML")
                    review.publication_status = "published"
                    review.published_at = now
                    review.channel_message_id = sent.message_id
                except Exception as exc:
                    review.last_error = str(exc)[:500]
                    logger.warning("Review publication failed id=%s: %s", review.id, exc)
            await session.commit()


async def create_review_if_missing(session, order: Order) -> None:
    exists = await session.execute(select(Review.id).where(Review.order_id == order.id))
    if exists.scalar_one_or_none() is not None:
        return
    delay = _int_setting("review_initial_delay_minutes", 1)
    now = datetime.now(timezone.utc)
    session.add(Review(
        order_id=order.id,
        user_id=order.user_id,
        status="awaiting_rating",
        publication_status="pending",
        requested_at=now,
        next_reminder_at=now + timedelta(minutes=delay),
    ))
