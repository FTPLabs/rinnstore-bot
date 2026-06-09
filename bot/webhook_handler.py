import hmac
import hashlib
import json
import logging
from aiohttp import web
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from .database import AsyncSessionFactory
from .services.payment_service import (
    process_cryptobot_webhook,
    process_rollypay_webhook,
    verify_rollypay_signature,
)
from .services.order_service import get_order, deliver_order
from .config import settings
from .utils.emoji import KEY, OK, STAR

logger = logging.getLogger(__name__)


def verify_cryptobot_signature(body: bytes, token: str, signature: str) -> bool:
    secret = hashlib.sha256(token.encode()).digest()
    expected = hmac.HMAC(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ─── CRYPTOBOT WEBHOOK ─────────────────────────────────────────────────────────

async def cryptobot_webhook(request: web.Request) -> web.Response:
    try:
        body = await request.read()
        signature = request.headers.get("crypto-pay-api-signature", "")

        from .services.settings_service import get_cached
        token = get_cached("cryptobot_token") or settings.cryptobot_token
        if not token:
            logger.error("CRYPTOBOT_TOKEN не задан — webhook отклонён")
            return web.Response(status=503, text="Service not configured")

        if not verify_cryptobot_signature(body, token, signature):
            logger.warning("CryptoBot: неверная подпись webhook")
            return web.Response(status=401, text="Invalid signature")

        data = json.loads(body)
        logger.info(f"CryptoBot webhook: {data.get('update_type')}")

        order_id = None
        async with AsyncSessionFactory() as session:
            processed = await process_cryptobot_webhook(session, data)
            if processed:
                payload_data = data.get("payload", {})
                order_id_str = payload_data.get("payload", "")
                if order_id_str and str(order_id_str).isdigit():
                    order_id = int(order_id_str)

        # ИСПРАВЛЕНИЕ #5: _notify_user_webhook получает НОВУЮ сессию (не ту, что уже закрыта)
        if order_id:
            await _notify_user_webhook(order_id, request.app.get("bot"))

        return web.Response(status=200, text="OK")

    except json.JSONDecodeError:
        logger.error("CryptoBot: невалидный JSON")
        return web.Response(status=400, text="Bad Request")
    except Exception as e:
        logger.exception(f"CryptoBot webhook error: {e}")
        return web.Response(status=500, text="Internal Server Error")


# ─── ROLLYPAY WEBHOOK ──────────────────────────────────────────────────────────

async def rollypay_webhook(request: web.Request) -> web.Response:
    try:
        body = await request.read()

        from .services.settings_service import get_cached
        signing_secret = get_cached("rollypay_signing_secret") or settings.rollypay_signing_secret

        # Проверяем подпись если секрет задан
        if signing_secret:
            signature = (
                request.headers.get("X-Signature")
                or request.headers.get("X-RollyPay-Signature")
                or ""
            )
            timestamp = request.headers.get("X-Timestamp", "")
            if not signature:
                logger.warning("RollyPay webhook: нет заголовка подписи")
                return web.Response(status=401, text="Missing signature")
            if not verify_rollypay_signature(body, signing_secret, signature, timestamp):
                logger.warning(f"RollyPay webhook: неверная подпись")
                return web.Response(status=401, text="Invalid signature")

        data = json.loads(body)
        logger.info(f"RollyPay webhook: status={data.get('status')}, payment_id={data.get('payment_id')}")

        order_id = None
        async with AsyncSessionFactory() as session:
            processed = await process_rollypay_webhook(session, data)
            if processed:
                order_id_str = str(data.get("order_id") or "")
                if order_id_str.isdigit():
                    order_id = int(order_id_str)

        # ИСПРАВЛЕНИЕ #5: notify через новую сессию
        if order_id:
            await _notify_user_webhook(order_id, request.app.get("bot"))

        return web.Response(status=200, text="OK")

    except json.JSONDecodeError:
        logger.error("RollyPay webhook: невалидный JSON")
        return web.Response(status=400, text="Bad Request")
    except Exception as e:
        logger.exception(f"RollyPay webhook error: {e}")
        return web.Response(status=500, text="Internal Server Error")


# ─── УВЕДОМЛЕНИЕ ПОЛЬЗОВАТЕЛЯ ──────────────────────────────────────────────────

async def _notify_user_webhook(order_id: int, bot: Bot | None) -> None:
    """
    ИСПРАВЛЕНИЕ #5: используем новуу сессию (не переданную извне после commit).
    Защита от двойной выдачи встроена в deliver_order (already_delivered_rows).
    """
    if not bot:
        return
    try:
        async with AsyncSessionFactory() as session:
            order = await get_order(session, order_id)
            if not order:
                return
            if order.status not in ("paid", "delivered", "partial"):
                logger.warning(
                    f"Webhook notify: заказ #{order_id} в статусе {order.status!r} — пропускаем"
                )
                return

            delivered = await deliver_order(session, order_id)
            if not delivered:
                logger.warning(
                    f"Webhook notify: deliver_order вернул пусто для заказа #{order_id}"
                )
                return

            items_text = "\n".join(f"{KEY} <code>{d['data']}</code>" for d in delivered)
            text = (
                f"{OK} <b>Заказ #{order_id} оплачен</b>\n\n"
                f"{items_text}\n\n"
                f"{STAR} Сохраните данные."
            )
            await bot.send_message(order.user_id, text, parse_mode="HTML")
    except Exception as e:
        logger.exception(f"Ошибка уведомления о заказе #{order_id}: {e}")


def setup_webhook_routes(app: web.Application) -> None:
    app.router.add_post("/webhook/cryptobot", cryptobot_webhook)
    app.router.add_post("/webhook/rollypay", rollypay_webhook)
