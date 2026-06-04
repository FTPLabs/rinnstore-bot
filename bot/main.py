import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from .config import settings
from .database import engine, Base
from .middlewares.db import DbSessionMiddleware
from .middlewares.auth import UserMiddleware
from .handlers import start, catalog, cart, payment, orders, promo
from .handlers.admin import main as admin_main
from .handlers.admin import products, orders_admin, users_admin, promos_admin, broadcast_admin
from .webhook_handler import setup_webhook_routes
from .services.admin_service import is_admin, log_action
from .database import AsyncSessionFactory
from .models import Admin, User
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def setup_initial_admins(bot: Bot):
    """Регистрирует начальных суперадминов из ADMIN_IDS."""
    admin_ids = settings.admin_list
    if not admin_ids:
        logger.warning("ADMIN_IDS не задан — у бота нет администраторов!")
        return

    async with AsyncSessionFactory() as session:
        for admin_id in admin_ids:
            result = await session.execute(select(Admin).where(Admin.user_id == admin_id))
            if not result.scalar_one_or_none():
                user_result = await session.execute(select(User).where(User.id == admin_id))
                if not user_result.scalar_one_or_none():
                    user = User(id=admin_id, first_name="Admin", referral_code=f"ADMIN{admin_id}")
                    session.add(user)
                    await session.flush()

                admin = Admin(user_id=admin_id, role="superadmin")
                session.add(admin)
                await session.commit()
                logger.info(f"Добавлен суперадмин: {admin_id}")


async def create_tables():
    async with engine.begin() as conn:
        pass


async def main():
    logger.info("Запуск бота...")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.update.middleware(DbSessionMiddleware())
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(cart.router)
    dp.include_router(payment.router)
    dp.include_router(orders.router)
    dp.include_router(promo.router)
    dp.include_router(admin_main.router)
    dp.include_router(products.router)
    dp.include_router(orders_admin.router)
    dp.include_router(users_admin.router)
    dp.include_router(promos_admin.router)
    dp.include_router(broadcast_admin.router)

    await setup_initial_admins(bot)

    aiohttp_app = web.Application()
    aiohttp_app["bot"] = bot
    setup_webhook_routes(aiohttp_app)

    runner = web.AppRunner(aiohttp_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.port)
    await site.start()
    logger.info(f"Webhook-сервер запущен на порту {settings.port}")

    me = await bot.get_me()
    logger.info(f"Бот @{me.username} запущен в режиме polling")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
