import random
import string
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from ..models import User

logger = logging.getLogger(__name__)


def generate_referral_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


async def get_or_create_user(session: AsyncSession, tg_user, referred_by_code: str = None) -> User:
    result = await session.execute(select(User).where(User.id == tg_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        try:
            code = generate_referral_code()
            referred_by_id = None
            if referred_by_code:
                ref_result = await session.execute(
                    select(User).where(User.referral_code == referred_by_code.upper())
                )
                referrer = ref_result.scalar_one_or_none()
                if referrer and referrer.id != tg_user.id:
                    referred_by_id = referrer.id

            user = User(
                id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language_code=getattr(tg_user, "language_code", "ru"),
                referral_code=code,
                referred_by=referred_by_id,
            )
            session.add(user)
            await session.commit()
        except IntegrityError:
            # ИСПРАВЛЕНИЕ #6: ловим только IntegrityError (race condition при одновременном /start)
            await session.rollback()
            result = await session.execute(select(User).where(User.id == tg_user.id))
            user = result.scalar_one()
        except Exception as e:
            # ИСПРАВЛЕНИЕ #6: логируем реальные ошибки, не глотаем молча
            logger.error(f"Ошибка создания пользователя {tg_user.id}: {e}", exc_info=True)
            await session.rollback()
            raise
    else:
        changed = (
            user.username != tg_user.username
            or user.first_name != tg_user.first_name
            or user.last_name != tg_user.last_name
        )
        if changed:
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
            await session.commit()

    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_referral_count(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count(User.id)).where(User.referred_by == user_id)
    )
    return result.scalar() or 0
