import aiohttp
import json
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

# Кэш курса: обновляется каждые 5 минут
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
    """Проверяет HMAC-SHA256 подпись вебхука RollyPay."""
    try:
        payload = (timestamp.encode("utf-8") + b"." + body) if timestamp else body
        expected = hmac.HMAC(
            signing_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature.lower())
    except Exception as e:
        logger.error(f"RollyPay signature verify error: {e}")
        return False


async def create_rollypay_invoice(
    session: AsyncSession,
    order: Order,
    webhook_host: str,
    user_id: int | None = None,
) -> "Payment | None":
    """Создаёт платёж через RollyPay HTTP API (рублёвый, СБП)."""
    from ..services.settings_service import get_cached

    api_key = get_cached("rollypay_api_key") or settings.rollypay_api_key
    terminal_id = get_cached("rollypay_terminal_id") or settings.rollypay_terminal_id
    api_url = settings.rollypay_api_url

    if not api_key:
        logger.error("RollyPay: rollypay_api_key не задан")
        return None

    payload: dict = {
        "amount": str(order.total_amount),
        "payment_currency": "RUB",
        "order_id": str(order.id),
        "payment_method": "sbp",
        "description": f"Заказ #{order.id} · RINN STORE",
        "redirect_url": "https://t.me/rinnnstore_bot",
    }
    if terminal_id:
        payload["terminal_id"] = terminal_id
    if user_id:
        payload["customer_id"] = str(user_id)
    if webhook_host:
        payload["webhook_url"] = f"{webhook_host}/webhook/rollypay"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            async with http.post(
                f"{api_url}/payments",
                headers={
                    "X-API-Key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            ) as resp:
                http_status = resp.status
                raw_body = await resp.text()
    except Exception as e:
        logger.error(f"RollyPay createPayment error: {e}")
        return None


    logger.info(f"RollyPay HTTP {http_status}, body: {raw_body[:500]!r}")
    if not raw_body.strip():
        logger.error(f"RollyPay: HTTP {http_status} — пустой ответ. Проверьте API URL и API Key.")
        return None
    try:
        resp_data = json.loads(raw_body)
    except Exception as _pe:
        logger.error(f"RollyPay: JSON parse error (HTTP {http_status}): {_pe}. Body: {raw_body[:300]!r}")
        return None

    if http_status not in (200, 201):
        logger.error(f"RollyPay: HTTP {http_status}: {resp_data}")
        return None

    pay_url = (
        resp_data.get("payment_url")
        or resp_data.get("pay_url")
        or resp_data.get("url")
        or resp_data.get("link")
        or resp_data.get("redirect_url")
    )
    payment_id = str(
        resp_data.get("payment_id")
        or resp_data.get("id")
        or resp_data.get("uuid")
        or f"rp_{order.id}"
    )

    if not pay_url:
        logger.error(f"RollyPay: нет payment_url в ответе: {resp_data}")
        return None

    payment = Payment(
        order_id=order.id,
        provider="rollypay",
        provider_invoice_id=payment_id,
        amount=order.total_amount,
        currency="RUB",
        status="pending",
        pay_url=pay_url,
        payload=resp_data,
    )
    session.add(payment)
    await session.commit()
    logger.info(f"RollyPay invoice создан: order={order.id}, id={payment_id}, url={pay_url}")
    return payment


async def check_rollypay_payment(payment_id: str, api_key: str) -> str:
    """Проверяет статус платежа RollyPay через HTTP API.
    Возвращает: paid | created | failed | error"""
    api_url = settings.rollypay_api_url
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as http:
            async with http.get(
                f"{api_url}/payments/{payment_id}",
                headers={
                    "X-API-Key": api_key,
                    "Accept": "application/json",
                },
            ) as resp:
                check_status = resp.status
                check_raw = await resp.text()
    except Exception as e:
        logger.error(f"RollyPay check error (id={payment_id}): {e}")
        return "error"

    if not check_raw.strip():
        logger.error(f"RollyPay check: HTTP {check_status} — пустой ответ (id={payment_id})")
        return "error"
    try:
        data = json.loads(check_raw)
    except Exception as _pe:
        logger.error(f"RollyPay check: JSON parse error (HTTP {check_status}): {_pe}")
        return "error"

    status = (data.get("status") or "").lower()
    if status in ("paid", "success", "completed"):
        return "paid"
    if status in ("created", "pending", "waiting", "processing"):
        return "created"
    if status in ("failed", "cancelled", "expired", "canceled"):
        return "failed"
    return status or "unknown"


async def process_rollypay_webhook(session: AsyncSession, data: dict) -> bool:
    """Обрабатывает вебхук от RollyPay."""
    status = (data.get("status") or "").lower()
    payment_id = str(data.get("payment_id") or data.get("id") or "")
    order_id_str = str(data.get("order_id") or "")

    if status not in ("paid", "success", "completed"):
        logger.info(f"RollyPay webhook: статус {status!r} — пропускаем")
        return False

    result = await session.execute(
        select(Payment).where(
            Payment.provider == "rollypay",
            Payment.provider_invoice_id == payment_id,
        )
    )
    payment = result.scalars().first()

    if not payment and order_id_str.isdigit():
        result = await session.execute(
            select(Payment).where(
                Payment.order_id == int(order_id_str),
                Payment.provider == "rollypay",
            )
        )
        payment = result.scalars().first()

    if not payment:
        logger.warning(f"RollyPay webhook: платёж не найден (id={payment_id}, order={order_id_str})")
        return False

    if payment.status == "paid":
        return True

    idempotency_key = f"rollypay_{payment_id or order_id_str}_{status}"
    existing = await session.execute(
        select(PaymentEvent).where(PaymentEvent.idempotency_key == idempotency_key)
    )
    if existing.scalar_one_or_none():
        logger.info(f"RollyPay webhook: событие {idempotency_key} уже обработано")
        return True

    event = PaymentEvent(
        payment_id=payment.id,
        event_type="payment_paid",
        payload=data,
        processed=True,
        idempotency_key=idempotency_key,
    )
    session.add(event)
    await mark_payment_paid(session, payment)
    logger.info(f"RollyPay платёж {payment_id} для заказа #{payment.order_id} подтверждён")
    return True
