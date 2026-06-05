import aiohttp
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from ..models import Payment, PaymentEvent, Order
from ..config import settings

CRYPTO_CURRENCY = "USDT"
RUB_TO_USDT = Decimal("0.011")


def rub_to_usdt(rub_amount: Decimal) -> str:
    usdt = rub_amount * RUB_TO_USDT
    return str(round(usdt, 2))


async def create_cryptobot_invoice(session: AsyncSession, order: Order) -> Payment | None:
    amount_usdt = rub_to_usdt(order.total_amount)

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

    from ..services.settings_service import get_cached, get_setting
    token = get_cached("cryptobot_token") or settings.cryptobot_token
    if not token:
        return None

    headers = {"Crypto-Pay-API-Token": token}

    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                f"{settings.cryptobot_api_url}/createInvoice",
                json=payload,
                headers=headers,
            ) as resp:
                data = await resp.json()
    except Exception:
        return None

    if not data.get("ok"):
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
    """Проверяет статус инвойса через CryptoBot API. Возвращает: active | paid | expired | cancelled"""
    from ..services.settings_service import get_cached
    token = get_cached("cryptobot_token") or settings.cryptobot_token
    headers = {"Crypto-Pay-API-Token": token}
    params = {"invoice_ids": invoice_id}

    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                f"{settings.cryptobot_api_url}/getInvoices",
                params=params,
                headers=headers,
            ) as resp:
                data = await resp.json()
    except Exception:
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
    Обрабатывает webhook от CryptoBot.
    Идемпотентно — проверяет по invoice_id.
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
