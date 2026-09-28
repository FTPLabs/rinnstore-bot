"""FreeKassa REST API integration based on https://docs.freekassa.net/."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Order, Payment
from .settings_service import get_cached

logger = logging.getLogger(__name__)
API_URL = "https://api.fk.life/v1"


def _settings() -> dict[str, str]:
    """Load credentials without ever returning them in an error message."""
    return {
        "shop_id": str(get_cached("freekassa_shop_id") or settings.freekassa_shop_id).strip(),
        "api_key": str(get_cached("freekassa_api_key") or settings.freekassa_api_key).strip(),
        "payer_ip": str(get_cached("freekassa_payer_ip") or settings.freekassa_payer_ip).strip(),
    }


def is_freekassa_api_enabled() -> bool:
    config = _settings()
    return bool(config["shop_id"] and config["api_key"] and config["payer_ip"])


def freekassa_api_signature(data: dict[str, object], api_key: str) -> str:
    """HMAC-SHA256 of alphabetically sorted request values, per FreeKassa docs."""
    unsigned = {key: value for key, value in data.items() if key != "signature" and value is not None}
    source = "|".join(str(unsigned[key]) for key in sorted(unsigned))
    return hmac.new(api_key.encode("utf-8"), source.encode("utf-8"), hashlib.sha256).hexdigest()


async def _request(path: str, payload: dict[str, object], api_key: str) -> dict | None:
    """Make one signed JSON request to the official FreeKassa API."""
    data = dict(payload)
    # FreeKassa requires a nonce greater than the previous request. A nanosecond
    # timestamp avoids collisions between concurrent callbacks in one process.
    data["nonce"] = time.time_ns()
    data["signature"] = freekassa_api_signature(data, api_key)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            async with http.post(f"{API_URL}{path}", json=data) as response:
                status = response.status
                raw = await response.text()
    except Exception as exc:
        logger.error("FreeKassa API request %s failed: %s", path, exc)
        return None

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("FreeKassa API request %s returned non-JSON (HTTP %s)", path, status)
        return None
    if status != 200 or body.get("type") != "success":
        logger.error(
            "FreeKassa API request %s failed (HTTP %s): %s",
            path,
            status,
            body.get("message", "unknown error"),
        )
        return None
    return body


async def get_freekassa_currencies() -> list[dict]:
    """Return payment methods enabled for this shop via the official API."""
    config = _settings()
    if not config["shop_id"] or not config["api_key"]:
        return []
    try:
        shop_id = int(config["shop_id"])
    except ValueError:
        logger.error("FreeKassa shop ID must be numeric")
        return []
    response = await _request("/currencies", {"shopId": shop_id}, config["api_key"])
    if not response:
        return []
    return [item for item in response.get("currencies", []) if item.get("is_enabled")]


async def create_freekassa_invoice(
    session: AsyncSession,
    order: Order,
    *,
    payer_email: str,
    currency_id: int,
    currency: str,
) -> Payment | None:
    """Create an order at `/orders/create` and persist its official location URL."""
    config = _settings()
    if not is_freekassa_api_enabled():
        logger.error("FreeKassa API configuration is incomplete")
        return None
    try:
        shop_id = int(config["shop_id"])
    except ValueError:
        logger.error("FreeKassa shop ID must be numeric")
        return None

    amount = f"{Decimal(str(order.total_amount)):.2f}"
    merchant_payment_id = f"rinn-{order.id}"
    response = await _request(
        "/orders/create",
        {
            "shopId": shop_id,
            "paymentId": merchant_payment_id,
            "i": currency_id,
            "email": payer_email,
            "ip": config["payer_ip"],
            "amount": amount,
            "currency": currency,
        },
        config["api_key"],
    )
    if not response or response.get("orderId") is None or not response.get("location"):
        logger.error("FreeKassa API did not return orderId and location")
        return None

    payment = Payment(
        order_id=order.id,
        provider="freekassa",
        provider_invoice_id=str(response["orderId"]),
        amount=Decimal(amount),
        currency=currency,
        status="pending",
        pay_url=str(response["location"]),
        payload={
            "merchant_payment_id": merchant_payment_id,
            "currency_id": currency_id,
            "order_hash": response.get("orderHash"),
        },
    )
    session.add(payment)
    await session.commit()
    return payment


async def check_freekassa_invoice(payment: Payment) -> str:
    """Read the invoice status from `/orders`; return paid, pending, failed or error."""
    config = _settings()
    if not config["shop_id"] or not config["api_key"]:
        return "error"
    try:
        shop_id = int(config["shop_id"])
    except ValueError:
        return "error"
    response = await _request(
        "/orders",
        {"shopId": shop_id, "orderId": payment.provider_invoice_id},
        config["api_key"],
    )
    if not response:
        return "error"
    orders = response.get("orders") or []
    if not orders:
        return "pending"
    status = str(orders[0].get("status", "")).lower()
    # FreeKassa documents successful orders with status 1.
    if status in {"1", "paid", "success", "completed"}:
        return "paid"
    if status in {"-1", "failed", "cancelled", "canceled", "expired"}:
        return "failed"
    return "pending"
