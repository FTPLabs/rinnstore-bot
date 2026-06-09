import logging
  from decimal import Decimal
  from datetime import datetime, timezone
  from sqlalchemy.ext.asyncio import AsyncSession
  from sqlalchemy import select, update, or_, func
  from ..models import Order, OrderItem, Product, ProductItem, DeliveredItem, PromoCode, User

  logger = logging.getLogger(__name__)

  REFERRAL_BONUS_PERCENT = Decimal("5")


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
              ).with_for_update()
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
                      pct = promo.discount_value
                      if Decimal("0") < pct <= Decimal("100"):
                          discount = total * pct / Decimal("100")
                      else:
                          logger.warning(f"Promo {promo.code}: invalid percent {pct}")
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


  async def get_order(session: AsyncSession, order_id: int) -> "Order | None":
      result = await session.execute(select(Order).where(Order.id == order_id))
      return result.scalar_one_or_none()


  async def get_user_orders(session: AsyncSession, user_id: int, limit: int = 10) -> list:
      result = await session.execute(
          select(Order)
          .where(Order.user_id == user_id)
          .order_by(Order.created_at.desc())
          .limit(limit)
      )
      return result.scalars().all()


  async def cancel_order(session: AsyncSession, order_id: int) -> None:
      result = await session.execute(
          select(Order).where(Order.id == order_id).with_for_update()
      )
      order = result.scalar_one_or_none()
      if not order:
          return
      if order.promo_code_id:
          await session.execute(
              update(PromoCode)
              .where(PromoCode.id == order.promo_code_id, PromoCode.used_count > 0)
              .values(used_count=PromoCode.used_count - 1)
          )
      await session.execute(
          update(Order).where(Order.id == order_id).values(status="cancelled")
      )
      await session.execute(
          update(ProductItem)
          .where(
              ProductItem.order_id == order_id,
              ProductItem.is_sold == False,
          )
          .values(is_reserved=False, order_id=None, reserved_until=None)
      )
      await session.commit()


  async def deliver_order(session: AsyncSession, order_id: int) -> list[dict]:
      result = await session.execute(
          select(Order).where(Order.id == order_id).with_for_update()
      )
      order = result.scalar_one_or_none()
      if not order:
          return []

      already_result = await session.execute(
          select(DeliveredItem).where(DeliveredItem.order_id == order_id).with_for_update()
      )
      already_delivered_rows = already_result.scalars().all()
      if already_delivered_rows:
          out = []
          for delivered in already_delivered_rows:
              pi_result = await session.execute(
                  select(ProductItem).where(ProductItem.id == delivered.product_item_id)
              )
              pi = pi_result.scalar_one_or_none()
              if pi:
                  out.append({"data": pi.data, "product_item_id": pi.id})
          return out

      oi_result = await session.execute(
          select(OrderItem).where(OrderItem.order_id == order_id)
      )
      order_items = oi_result.scalars().all()

      delivered_list = []
      out_of_stock = False

      for order_item in order_items:
          prod_result = await session.execute(
              select(Product).where(Product.id == order_item.product_id)
          )
          product = prod_result.scalar_one_or_none()

          for _ in range(order_item.quantity):
              # Логика одинакова для unlimited и обычных товаров:
              # берём любой доступный item (не продан, не зарезервирован)
              pi_result = await session.execute(
                  select(ProductItem).where(
                      ProductItem.product_id == order_item.product_id,
                      ProductItem.is_sold == False,
                      ProductItem.is_reserved == False,
                  ).limit(1).with_for_update(skip_locked=True)
              )
              pi = pi_result.scalar_one_or_none()
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
                  delivered_list.append({
                      "data": "⚠️ Нет на складе. Напишите в поддержку.",
                      "product_item_id": None,
                  })

      order.status = "partial" if out_of_stock else "delivered"

      await session.execute(
          update(User)
          .where(User.id == order.user_id)
          .values(total_spent=User.total_spent + order.total_amount)
      )

      if not out_of_stock:
          buyer_result = await session.execute(
              select(User).where(User.id == order.user_id)
          )
          buyer = buyer_result.scalar_one_or_none()
          if buyer and buyer.referred_by:
              prev_result = await session.execute(
                  select(func.count(Order.id)).where(
                      Order.user_id == order.user_id,
                      Order.status == "delivered",
                      Order.id != order_id,
                  )
              )
              prev_delivered = prev_result.scalar() or 0
              if prev_delivered == 0:
                  bonus = (order.total_amount * REFERRAL_BONUS_PERCENT / Decimal("100")).quantize(Decimal("0.01"))
                  await session.execute(
                      update(User)
                      .where(User.id == buyer.referred_by)
                      .values(referral_bonus=User.referral_bonus + bonus)
                  )
                  logger.info(f"Referral bonus {bonus} credited to user {buyer.referred_by}")

      await session.commit()
      return delivered_list
  