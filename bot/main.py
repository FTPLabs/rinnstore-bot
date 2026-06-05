import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web

from .config import settings
from .database import engine, Base
from .middlewares.db import DbSessionMiddleware
from .middlewares.auth import UserMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .handlers import start, catalog, cart, payment, orders, promo
from .handlers import onboarding
from .handlers.admin import main as admin_main
from .handlers.admin import products, orders_admin, users_admin, promos_admin, broadcast_admin
from .handlers.admin import settings_admin
from .webhook_handler import setup_webhook_routes
from .database import AsyncSessionFactory
from .models import Admin, User
from .services.settings_service import load_all_settings
from .utils.backup import backup_scheduler
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def setup_initial_admins():
    admin_ids = settings.admin_list
    if not admin_ids:
        logger.warning("ADMIN_IDS не задан")
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
                logger.info(f"Суперадмин зарегистрирован: {admin_id}")


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Таблицы и индексы созданы/проверены")


async def main():
    logger.info("Запуск бота...")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)

    # Middleware (порядок важен: db → throttling → auth)
    dp.update.middleware(DbSessionMiddleware())
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.callback_query.middleware(ThrottlingMiddleware(rate_limit=0.3))
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.include_router(onboarding.router)
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
    dp.include_router(settings_admin.router)

    await create_tables()
    await setup_initial_admins()

    async with AsyncSessionFactory() as session:
        await load_all_settings(session)
        logger.info("Настройки загружены из БД")

    aiohttp_app = web.Application()
    aiohttp_app["bot"] = bot
    setup_webhook_routes(aiohttp_app)

    runner = web.AppRunner(aiohttp_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.port)
    await site.start()
    logger.info(f"Webhook-сервер запущен на порту {settings.port}")

    me = await bot.get_me()
    logger.info(f"Бот @{me.username} запущен и готов к работе")

    from .services.settings_service import get_cached
    try:
        backup_hours = int(get_cached("backup_interval") or "6")
    except (ValueError, TypeError):
        backup_hours = 6
        logger.warning("Некорректное значение backup_interval, используем 6ч")

    backup_task = asyncio.create_task(
        backup_scheduler(settings.database_url, interval_hours=backup_hours)
    )

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        backup_task.cancel()
        try:
            await backup_task
        except asyncio.CancelledError:
            pass
        await runner.cleanup()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
