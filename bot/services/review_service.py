import asyncio
import html
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ..database import AsyncSessionFactory
from ..models import Review, Order, User, Admin
from ..services.settings_service import get_cached
from ..keyboards.review import moderation_kb, rating_kb
from ..utils.i18n import t

logger = logging.getLogger(__name__)
BUY_URL = "https://t.me/rinnnstore_bot?start=catalog"
KEY_EMOJI = '<tg-emoji emoji-id="5893311672667345793">🔑</tg-emoji>'
STAR_EMOJI = '<tg-emoji emoji-id="5893034681636491040">⭐</tg-emoji>'


def _int_setting(key: str, default: int) -> int:
    try:
        return max(0, int(get_cached(key) or default))
    except (TypeError, ValueError):
        return default


def _product_names(order) -> str:
    return ", ".join(item.product.name for item in (order.items if order else []) if item.product) or "—"


def format_review_text(review: Review, order: Order | None, buyer: User | None, bot_username: str) -> str:
    product = html.escape(_product_names(order))
    amount = html.escape(str(order.total_amount if order else "—"))
    comment = html.escape(review.comment or "Комментарий не оставлен")
    author = "Анонимный покупатель" if review.anonymous else (f"@{buyer.username}" if buyer and buyer.username else (buyer.first_name if buyer else "Покупатель"))
    return (
        f"<b>{KEY_EMOJI} ОТЗЫВ В БОТЕ @{html.escape(bot_username)}</b>\n\n"
        f"<b>Купленный товар:</b> {product}\n"
        f"<b>Стоимость товара:</b> {amount} ₽\n"
        f"<b>Номер заказа:</b> #{review.order_id}\n"
        f"<b>Покупатель:</b> {html.escape(author)}\n"
        f"<b>Оценка:</b> {STAR_EMOJI * (review.rating or 0)}\n"
        f"<b>Отзыв:</b> {comment}"
    )


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
            select(Review).options(selectinload(Review.order).selectinload(Order.items)).where(
                Review.status == "awaiting_rating",
                Review.next_reminder_at <= now,
                Review.reminders_sent < max_reminders,
            ).order_by(Review.next_reminder_at).limit(50).with_for_update(skip_locked=True)
        )
        reviews = result.scalars().all()
        for review in reviews:
            try:
                buyer = await session.get(User, review.user_id)
                await bot.send_message(
                    review.user_id,
                    t(buyer or "ru", "review_prompt", product=_product_names(review.order), amount=review.order.total_amount if review.order else "—", order_id=review.order_id),
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
            select(Review).options(selectinload(Review.order).selectinload(Order.items)).where(
                Review.status == "completed",
                Review.moderation_status == "pending",
            ).order_by(Review.completed_at).limit(50).with_for_update(skip_locked=True)
        )
        completed = result.scalars().all()
        admins = (await session.execute(select(Admin.user_id))).scalars().all()
        if admins:
            me = await bot.get_me()
            for review in completed:
                try:
                    buyer = await session.get(User, review.user_id)
                    text = format_review_text(review, review.order, buyer, me.username or "rinnnstore_bot")
                    sent_ids = []
                    for admin_id in admins:
                        sent = await bot.send_message(admin_id, text, reply_markup=moderation_kb(review.id), parse_mode="HTML")
                        sent_ids.append(sent.message_id)
                    review.moderation_status = "notified"
                    review.admin_message_id = sent_ids[0] if sent_ids else None
                except Exception as exc:
                    review.last_error = str(exc)[:500]
                    logger.warning("Review moderation notification failed id=%s: %s", review.id, exc)
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
        moderation_status="pending",
        requested_at=now,
        next_reminder_at=now + timedelta(minutes=delay),
    ))
