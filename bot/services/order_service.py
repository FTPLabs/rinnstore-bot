from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_
from ..models import Order, OrderItem, Product, ProductItem, DeliveredItem, PromoCode, User


async def create_order(
    session: AsyncSession,
    user_id: int,
    cart_items: list[dict],
    promo_code: str | None = None,
) -> Order:
    total = Decimal("0")
    discount = Decimal("0")
    promo_id = None

    for item in cart_items:
        total += Decimal(str(item["price"])) * item["qty"]

    if promo_code:
        result = await session.execute(
            select(PromoCode).where(
                PromoCode.code == promo_code.upper(),
                PromoCode.is_active == True,
                or_(
                    PromoCode.expires_at == None,
                    PromoCode.expires_at > datetime.now(timezone.utc),
                ),
            )
        )
        promo = result.scalar_one_or_none()
        if promo and total >= (promo.min_order_amount or Decimal("0")):
            updated = await session.execute(
                update(PromoCode)
                .where(
                    PromoCode.id == promo.id,
                    or_(
                        PromoCode.max_uses == None,
                        PromoCode.used_count < PromoCode.max_uses,
                    ),
                )
                .values(used_count=PromoCode.used_count + 1)
                .returning(PromoCode.id)
            )
            if updated.scalar_one_or_none():
                if promo.discount_type == "percent":
                    discount = total * promo.discount_value / 100
                else:
                    discount = min(promo.discount_value, total)
                promo_id = promo.id

    order = Order(
        user_id=user_id,
        status="pending",
        total_amount=max(total - discount, Decimal("0")),
        promo_code_id=promo_id,
        discount_amount=discount,
    )
    session.add(order)
    await session.flush()

    for item in cart_items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=item["product_id"],
            quantity=item["qty"],
            unit_price=Decimal(str(item["price"])),
        )
        session.add(order_item)

    await session.commit()
    await session.refresh(order)
    return order


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(
        select(Order).where(Order.id == order_id)
    )
    return result.scalar_one_or_none()


async def get_user_orders(session: AsyncSession, user_id: int, limit: int = 10) -> list[Order]:
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def cancel_order(session: AsyncSession, order_id: int) -> None:
    await session.execute(
        update(Order).where(Order.id == order_id).values(status="cancelled")
    )
    await session.execute(
        update(ProductItem).where(ProductItem.order_id == order_id).values(
            is_reserved=False, is_sold=False, order_id=None, reserved_until=None
        )
    )
    await session.commit()


async def deliver_order(session: AsyncSession, order_id: int) -> list[dict]:
    """
    Идемпотентная выдача товаров.
    with_for_update на Order исключает гонку webhook + ручная проверка.
    """
    result = await session.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        return []

    already_delivered = []
    for delivered in order.delivered_items:
        item_result = await session.execute(
            select(ProductItem).where(ProductItem.id == delivered.product_item_id)
        )
        pi = item_result.scalar_one_or_none()
        if pi:
            already_delivered.append({"data": pi.data, "product_item_id": pi.id})

    if already_delivered:
        return already_delivered

    delivered_list = []
    out_of_stock = False
    for order_item in order.items:
        for _ in range(order_item.quantity):
            result = await session.execute(
                select(ProductItem).where(
                    ProductItem.product_id == order_item.product_id,
                    ProductItem.is_sold == False,
                    ProductItem.is_reserved == False,
                ).limit(1).with_for_update(skip_locked=True)
            )
            pi = result.scalar_one_or_none()
            if pi:
                pi.is_sold = True
                pi.is_reserved = False
                pi.sold_at = datetime.now(timezone.utc)
                pi.order_id = order_id
                delivered = DeliveredItem(
                    order_id=order_id,
                    order_item_id=order_item.id,
                    product_item_id=pi.id,
                )
                session.add(delivered)
                delivered_list.append({"data": pi.data, "product_item_id": pi.id})
            else:
                out_of_stock = True
                delivered_list.append({"data": "⚠️ Нет на складе. Напишите в поддержку.", "product_item_id": None})

    order.status = "partial" if out_of_stock else "delivered"

    if not out_of_stock:
        await session.execute(
            update(User)
            .where(User.id == order.user_id)
            .values(total_spent=User.total_spent + order.total_amount)
        )

    await session.commit()
    return delivered_list
