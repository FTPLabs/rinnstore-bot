import aiohttp
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

# Кэш курса: обновляется каждые 5 минут через CryptoBot API
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
                # CryptoBot возвращает курс USDT/RUB как source=USDT, target=RUB
                if item.get("source") == "USDT" and item.get("target") == "RUB":
                    rate_rub_per_usdt = Decimal(str(item["rate"]))
                    # Инвертируем: RUB/USDT = 1 / (USDT/RUB)
                    rub_to_usdt_rate = Decimal("1") / rate_rub_per_usdt
                    _rate_cache["rate"] = rub_to_usdt_rate
                    _rate_cache["updated_at"] = now
                    logger.info(f"Курс USDT обновлён: 1 RUB = {rub_to_usdt_rate:.6f} USDT")
                    return rub_to_usdt_rate
    except Exception as e:
        logger.warning(f"Не удалось получить курс USDT: {e}, используем кэш")

    return _rate_cache["rate"]


async def rub_to_usdt(rub_amount: Decimal) -> str:
    rate = await get_usdt_rate()
    usdt = rub_amount * rate
    return str(round(usdt, 2))


async def create_cryptobot_invoice(session: AsyncSession, order: Order) -> Payment | None:
    amount_usdt = await rub_to_usdt(order.total_amount)

    payload = {
        "currency_type": "crypto",
        "crypto_asset": CRYPTO_CURRENCY,
        "amount": amount_usdt,
        "description": f"Заказ #{order.id}",
        "payload": str(order.id),
        "allow_comments": False,
        "allow_anonymous": False,
        "expires_in": 3600,
    }

    from ..services.settings_service import get_cached
    token = get_cached("cryptobot_token") or settings.cryptobot_token
    if not token:
        return None

    headers = {"Crypto-Pay-API-Token": token}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
            async with http.post(
                f"{settings.cryptobot_api_url}/createInvoice",
                json=payload,
                headers=headers,
            ) as resp:
                data = await resp.json()
    except Exception as e:
        logger.error(f"CryptoBot createInvoice error: {e}")
        return None

    if not data.get("ok"):
        logger.error(f"CryptoBot createInvoice failed: {data}")
        return None

    result_data = data["result"]

    payment = Payment(
        order_id=order.id,
        provider="cryptobot",
        provider_invoice_id=str(result_data["invoice_id"]),
        amount=Decimal(amount_usdt),
        currency=CRYPTO_CURRENCY,
        status="pending",
        pay_url=result_data["bot_invoice_url"],
        payload=result_data,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def check_cryptobot_invoice(invoice_id: str) -> str:
    """Проверяет статус инвойса. Возвращает: active | paid | expired | cancelled | error"""
    from ..services.settings_service import get_cached
    token = get_cached("cryptobot_token") or settings.cryptobot_token
    if not token:
        return "error"

    headers = {"Crypto-Pay-API-Token": token}
    params = {"invoice_ids": invoice_id}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
            async with http.get(
                f"{settings.cryptobot_api_url}/getInvoices",
                params=params,
                headers=headers,
            ) as resp:
                data = await resp.json()
    except Exception as e:
        logger.error(f"CryptoBot getInvoices error: {e}")
        return "error"

    if not data.get("ok"):
        return "error"

    items = data["result"].get("items", [])
    if not items:
        return "not_found"

    return items[0].get("status", "unknown")


async def get_payment_by_order(session: AsyncSession, order_id: int) -> Payment | None:
    result = await session.execute(
        select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc())
    )
    return result.scalars().first()


async def mark_payment_paid(session: AsyncSession, payment: Payment) -> None:
    payment.status = "paid"
    payment.paid_at = datetime.now(timezone.utc)
    await session.execute(
        update(Order).where(Order.id == payment.order_id).values(status="paid")
    )
    await session.commit()


async def process_cryptobot_webhook(session: AsyncSession, data: dict) -> bool:
    """
    Обрабатывает webhook от CryptoBot. Идемпотентно — проверяет по invoice_id.
    """
    update_type = data.get("update_type")
    if update_type != "invoice_paid":
        return False

    payload_data = data.get("payload", {})
    invoice_id = str(payload_data.get("invoice_id", ""))
    idempotency_key = f"cryptobot_{invoice_id}"

    exists = await session.execute(
        select(PaymentEvent).where(PaymentEvent.idempotency_key == idempotency_key)
    )
    if exists.scalar_one_or_none():
        return False

    result = await session.execute(
        select(Payment).where(
            Payment.provider == "cryptobot",
            Payment.provider_invoice_id == invoice_id,
        )
    )
    payment = result.scalar_one_or_none()
    if not payment:
        return False

    if payment.status == "paid":
        return False

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
