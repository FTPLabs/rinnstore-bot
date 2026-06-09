import aiohttp
import asyncio
import hmac
import hashlib
import logging
import time
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from ..models import Payment, PaymentEvent, Order
from ..config import settings

logger = logging.getLogger(__name__)

CRYPTO_CURRENCY = "USDT"

# Кэш курса: обновляется каждые 5 минют
_rate_cache: dict = {"rate": Decimal("0.011"), "updated_at": 0.0}


async def get_usdt_rate() -> Decimal:
    """Получает актуальный курс RUB→USDT через CryptoBot API (кэш 5 мин)."""
    now = time.monotonic()
    if now - _rate_cache["updated_at"] < 300:
        return _rate_cache["rate"]

    from ..services.settings_service import get_cached
    token = get_cached("cryptobot_token") or settings.cryptobot_token
    if not token:
        return _rate_cache["rate"]

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as http:
            async with http.get(
                f"{settings.cryptobot_api_url}/getExchangeRates",
                headers={"Crypto-Pay-API-Token": token},
            ) as resp:
                data = await resp.json()

        if data.get("ok"):
            for item in data.get("result", []):
                if item.get("source") == "USDT" and item.get("target") == "RUB":
                    rate_rub_per_usdt = Decimal(str(item["rate"]))
                    if rate_rub_per_usdt > 0:
                        rate = (Decimal("1") / rate_rub_per_usdt).quantize(Decimal("0.000001"))
                        _rate_cache["rate"] = rate
                        _rate_cache["updated_at"] = now
                        logger.info(f"Курс RUB→USDT обновлён: {rate}")
                        return rate
    except Exception as e:
        logger.warning(f"Не удалось получить курс RUB→USDT: {e}")

    return _rate_cache["rate"]


async def get_payment_by_order(session: AsyncSession, order_id: int) -> "Payment | None":
    """Только pending — для создания нового инвойса."""
    result = await session.execute(
        select(Payment)
        .where(Payment.order_id == order_id, Payment.status == "pending")
        .order_by(Payment.created_at.desc())
    )
    return result.scalars().first()


async def get_payment_by_order_provider(
    session: AsyncSession, order_id: int, provider: str
) -> "Payment | None":
    """Только pending — для повторного использования ссылки на оплату."""
    result = await session.execute(
        select(Payment).where(
            Payment.order_id == order_id,
            Payment.provider == provider,
            Payment.status == "pending",
        ).order_by(Payment.created_at.desc())
    )
    return result.scalars().first()


async def get_payment_for_check(
    session: AsyncSession, order_id: int, provider: str
) -> "Payment | None":
    """pending ИЛИ paid — для проверки статуса оплаты пользователем.
    Нужно чтобы найти платёж после webhook, который уже пометил его paid,
    но deliver_order не выполнился (ошибка выдачи)."""
    result = await session.execute(
        select(Payment).where(
            Payment.order_id == order_id,
            Payment.provider == provider,
        ).order_by(Payment.created_at.desc())
    )
    return result.scalars().first()


# ─── CRYPTOBOT ─────────────────────────────────────────────────────────────────

async def create_cryptobot_invoice(session: AsyncSession, order: Order) -> "Payment | None":
    from ..services.settings_service import get_cached
    token = get_cached("cryptobot_token") or settings.cryptobot_token
    if not token:
        logger.error("CRYPTOBOT_TOKEN не задан")
        return None

    rate = await get_usdt_rate()
    # CryptoBot min = $0.01 USD. 0.01 USDT ≈ $0.00999 — под минимумом. Ставим 0.02 USDT.
    amount_usdt = (order.total_amount * rate).quantize(Decimal("0.000001"))
    if amount_usdt < Decimal("0.02"):
        amount_usdt = Decimal("0.02")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
            async with http.post(
                f"{settings.cryptobot_api_url}/createInvoice",
                headers={"Crypto-Pay-API-Token": token},
                json={
                    "asset": CRYPTO_CURRENCY,
                    "amount": str(amount_usdt),
                    "payload": str(order.id),
                    "description": f"Заказ #{order.id}",
                    "expires_in": 3600,
                },
            ) as resp:
                data = await resp.json()
    except Exception as e:
        logger.error(f"CryptoBot API error: {e}")
        return None

    if not data.get("ok"):
        logger.error(f"CryptoBot createInvoice failed: {data}")
        return None

    inv = data["result"]
    payment = Payment(
        order_id=order.id,
        provider="cryptobot",
        provider_invoice_id=str(inv["invoice_id"]),
        amount=amount_usdt,
        currency=CRYPTO_CURRENCY,
        status="pending",
        pay_url=inv.get("bot_invoice_url") or inv.get("pay_url"),
        payload=inv,
    )
    session.add(payment)
    await session.commit()
    return payment


async def check_cryptobot_invoice(invoice_id: str) -> str:
    from ..services.settings_service import get_cached
    token = get_cached("cryptobot_token") or settings.cryptobot_token
    if not token:
        return "error"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
            async with http.get(
                f"{settings.cryptobot_api_url}/getInvoices",
                headers={"Crypto-Pay-API-Token": token},
                params={"invoice_ids": invoice_id},
            ) as resp:
                data = await resp.json()
        if data.get("ok"):
            items = data["result"].get("items", [])
            if items:
                return items[0].get("status", "unknown")
    except Exception as e:
        logger.error(f"CryptoBot check error: {e}")
    return "error"


async def mark_payment_paid(session: AsyncSession, payment: Payment) -> None:
    payment.status = "paid"
    payment.paid_at = datetime.now(timezone.utc)
    result = await session.execute(select(Order).where(Order.id == payment.order_id))
    order = result.scalar_one_or_none()
    if order:
        order.status = "paid"
    await session.commit()


async def process_cryptobot_webhook(session: AsyncSession, data: dict) -> bool:
    if data.get("update_type") != "invoice_paid":
        return False

    payload_data = data.get("payload", {})
    invoice_id = str(payload_data.get("invoice_id", ""))

    result = await session.execute(
        select(Payment).where(Payment.provider_invoice_id == invoice_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        logger.warning(f"CryptoBot webhook: платёж {invoice_id} не найден")
        return False
    if payment.status == "paid":
        return True

    idempotency_key = f"cryptobot_{invoice_id}"
    existing = await session.execute(
        select(PaymentEvent).where(PaymentEvent.idempotency_key == idempotency_key)
    )
    if existing.scalar_one_or_none():
        logger.info(f"CryptoBot webhook: событие {idempotency_key} уже обработано")
        return True

    event = PaymentEvent(
        payment_id=payment.id,
        event_type="invoice_paid",
        payload=data,
        processed=True,
        idempotency_key=idempotency_key,
    )
    session.add(event)
    await mark_payment_paid(session, payment)
    return True


# ─── ROLLYPAY (прямые HTTP-запросы, без SDK) ───────────────────────────────────

def verify_rollypay_signature(body: bytes, signing_secret: str, signature: str, timestamp: str = "") -> bool:
    """Проверяет HMAC-SHA256 подпись вебхука Ролляпаэ.
    формула: HMAC-SHA256(signing_secret, X-Timestamp + "." + body)
    """
    try:
        payload = (timestamp.encode("utf-8") + b"." + body) if timestamp else body
        expected = hmac.new(
            signing_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature.lower())
    except Exception as e:
        logger.error(f"RollyPay signature verify error: {e}")
        return False
