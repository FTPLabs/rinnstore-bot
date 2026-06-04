"""
Webhook-обработчик для платёжных систем (CryptoBot).
Запускается вместе с ботом как aiohttp-сервер.
"""
import hmac
import hashlib
import json
import logging
from aiohttp import web
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from .database import AsyncSessionFactory
from .services.payment_service import process_cryptobot_webhook
from .services.order_service import get_order, deliver_order
from .config import settings

logger = logging.getLogger(__name__)


def verify_cryptobot_signature(body: bytes, token: str, signature: str) -> bool:
    """Проверяет подпись webhook от CryptoBot."""
    secret = hashlib.sha256(token.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()  # type: ignore
    return hmac.compare_digest(expected, signature)


async def cryptobot_webhook(request: web.Request) -> web.Response:
    """Принимает webhook от CryptoBot о статусе платежа."""
    try:
        body = await request.read()
        signature = request.headers.get("crypto-pay-api-signature", "")

        if settings.cryptobot_token:
            if not verify_cryptobot_signature(body, settings.cryptobot_token, signature):
                logger.warning("CryptoBot: неверная подпись webhook")
                return web.Response(status=401, text="Invalid signature")

        data = json.loads(body)
        logger.info(f"CryptoBot webhook: {data.get('update_type')}")

        async with AsyncSessionFactory() as session:
            processed = await process_cryptobot_webhook(session, data)

            if processed:
                payload_data = data.get("payload", {})
                order_id_str = payload_data.get("payload", "")
                if order_id_str and order_id_str.isdigit():
                    order_id = int(order_id_str)
                    await _notify_user_after_payment(session, order_id, request.app.get("bot"))

        return web.Response(status=200, text="OK")

    except json.JSONDecodeError:
        logger.error("CryptoBot: невалидный JSON в webhook")
        return web.Response(status=400, text="Bad Request")
    except Exception as e:
        logger.exception(f"CryptoBot webhook error: {e}")
        return web.Response(status=500, text="Internal Server Error")


async def _notify_user_after_payment(session: AsyncSession, order_id: int, bot: Bot | None):
    """Уведомляет пользователя и выдаёт товар после успешной оплаты."""
    if not bot:
        return
    try:
        order = await get_order(session, order_id)
        if not order or order.status not in ("paid", "delivered"):
            return

        delivered = await deliver_order(session, order_id)

        from .utils.emoji import KEY, OK, STAR, BAG
        items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)

        text = (
            f"{OK} <b>Оплата получена!</b>\n"
            f"{'━' * 16}\n\n"
            f"{BAG} <b>Ваши товары по заказу #{order_id}:</b>\n\n"
            f"{items_text}\n\n"
            f"{STAR} Спасибо за покупку! Сохраните данные."
        )
        await bot.send_message(order.user_id, text, parse_mode="HTML")
    except Exception as e:
        logger.exception(f"Ошибка уведомления пользователя: {e}")


def setup_webhook_routes(app: web.Application):
    app.router.add_post("/webhook/cryptobot", cryptobot_webhook)
