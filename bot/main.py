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
from .handlers import privacy
from .handlers import start, catalog, cart, payment, orders, promo, reviews
from .handlers import onboarding
from .handlers.admin import main as admin_main
from .handlers.admin import products, orders_admin, users_admin, promos_admin, broadcast_admin
from .handlers.admin import settings_admin
from .handlers.admin import catalog_admin
from .handlers.admin import reviews_admin
from .database import AsyncSessionFactory
from .models import Admin, User
from .services.settings_service import load_all_settings
from .services.custom_emoji_service import seed_custom_emojis, load_custom_emojis
from .utils.backup import backup_scheduler
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .webhook_handler import setup_webhook_routes
from .services.review_service import review_worker

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

    for admin_id in admin_ids:
        try:
            async with AsyncSessionFactory() as session:
                result = await session.execute(select(Admin).where(Admin.user_id == admin_id))
                if result.scalar_one_or_none():
                    continue
                user_result = await session.execute(select(User).where(User.id == admin_id))
                if not user_result.scalar_one_or_none():
                    user = User(id=admin_id, first_name="Admin", referral_code=f"ADMIN{admin_id}", terms_accepted=True, captcha_passed=True)
                    session.add(user)
                    await session.flush()
                admin = Admin(user_id=admin_id, role="superadmin")
                session.add(admin)
                await session.commit()
                logger.info(f"Суперадмин зарегистрирован: {admin_id}")
        except IntegrityError:
            logger.info(f"Суперадмин {admin_id} уже существует (race condition — игнорируем)")


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table, columns in {
            "categories": {"name_en": "VARCHAR(255)", "description_en": "TEXT"},
            "products": {"name_en": "VARCHAR(255)", "description_en": "TEXT"},
            "reviews": {"anonymous": "BOOLEAN NOT NULL DEFAULT 0", "moderation_status": "VARCHAR(32) NOT NULL DEFAULT 'pending'", "admin_message_id": "BIGINT"},
        }.items():
            existing = await conn.run_sync(
                lambda sync_conn, table=table: {
                    row[1] for row in sync_conn.exec_driver_sql(f"PRAGMA table_info({table})")
                }
            )
            for column, definition in columns.items():
                if column not in existing:
                    await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
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
    dp.include_router(reviews.router)
    dp.include_router(start.router)
    dp.include_router(privacy.router)
    dp.include_router(catalog.router)
    dp.include_router(cart.router)
    dp.include_router(payment.router)
    dp.include_router(orders.router)
    dp.include_router(promo.router)
    dp.include_router(admin_main.router)
    dp.include_router(catalog_admin.router)  # единый каталог — до products
    dp.include_router(products.router)
    dp.include_router(orders_admin.router)
    dp.include_router(users_admin.router)
    dp.include_router(promos_admin.router)
    dp.include_router(broadcast_admin.router)
    dp.include_router(settings_admin.router)
    dp.include_router(reviews_admin.router)

    await create_tables()
    await setup_initial_admins()

    async with AsyncSessionFactory() as session:
        await load_all_settings(session)
        added_emojis = await seed_custom_emojis(session)
        await load_custom_emojis(session)
        logger.info("ProtectStatus emoji catalog loaded (%s new records)", added_emojis)
        logger.info("Настройки загружены из БД")

    aiohttp_app = web.Application()
    aiohttp_app["bot"] = bot
    setup_webhook_routes(aiohttp_app)

    async def healthz(request):
        return web.json_response({"status": "ok"})

    aiohttp_app.router.add_get("/healthz", healthz)

    async def payment_success(request):
        return web.Response(
            text="<html><meta charset='utf-8'><title>Оплата успешна</title>"
                 "<h2>Оплата прошла успешно</h2><p>Вернитесь в Telegram-бот — заказ будет выдан после подтверждения.</p></html>",
            content_type="text/html",
        )

    async def payment_failure(request):
        return web.Response(
            text="<html><meta charset='utf-8'><title>Оплата не завершена</title>"
                 "<h2>Оплата не завершена</h2><p>Вернитесь в Telegram-бот и попробуйте другой способ оплаты.</p></html>",
            content_type="text/html",
        )

    aiohttp_app.router.add_get("/payment/success", payment_success)
    aiohttp_app.router.add_get("/payment/failure", payment_failure)

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

    await bot.delete_webhook(drop_pending_updates=False)
    backup_task = asyncio.create_task(
        backup_scheduler(settings.database_url, interval_hours=backup_hours)
    )
    review_task = asyncio.create_task(review_worker(bot))

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        backup_task.cancel()
        review_task.cancel()
        try:
            await backup_task
        except asyncio.CancelledError:
            pass
        try:
            await review_task
        except asyncio.CancelledError:
            pass
        await runner.cleanup()
        await bot.session.close()
        await storage.close()
        await engine.dispose()
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
