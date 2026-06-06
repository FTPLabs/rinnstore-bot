from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from ..models import (
    Admin, User, Product, ProductItem, Order, Category,
    PromoCode, AuditLog
)


async def is_admin(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(Admin).where(Admin.user_id == user_id))
    return result.scalar_one_or_none() is not None


async def get_admin(session: AsyncSession, user_id: int) -> Admin | None:
    result = await session.execute(select(Admin).where(Admin.user_id == user_id))
    return result.scalar_one_or_none()


async def get_stats(session: AsyncSession) -> dict:
    total_users = (await session.execute(select(func.count(User.id)))).scalar()
    total_orders = (await session.execute(select(func.count(Order.id)))).scalar()
    paid_orders = (await session.execute(
        select(func.count(Order.id)).where(Order.status.in_(["paid", "delivered"]))
    )).scalar()
    total_revenue = (await session.execute(
        select(func.sum(Order.total_amount)).where(Order.status.in_(["paid", "delivered"]))
    )).scalar() or Decimal("0")
    total_products = (await session.execute(select(func.count(Product.id)))).scalar()
    total_items = (await session.execute(
        select(func.count(ProductItem.id)).where(ProductItem.is_sold == False, ProductItem.is_reserved == False)
    )).scalar()
    return {
        "total_users": total_users,
        "total_orders": total_orders,
        "paid_orders": paid_orders,
        "total_revenue": total_revenue,
        "total_products": total_products,
        "available_items": total_items,
    }


async def get_all_products(session: AsyncSession) -> list[Product]:
    result = await session.execute(
        select(Product).order_by(Product.category_id, Product.sort_order, Product.name)
    )
    return result.scalars().all()


async def get_all_categories(session: AsyncSession) -> list[Category]:
    result = await session.execute(
        select(Category).order_by(Category.sort_order, Category.name)
    )
    return result.scalars().all()


async def create_category(session: AsyncSession, name: str, description: str = "") -> Category:
    cat = Category(name=name, description=description)
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


async def create_product(
    session: AsyncSession,
    category_id: int,
    name: str,
    description: str,
    price: Decimal,
    is_unlimited: bool = False,
) -> Product:
    product = Product(
        category_id=category_id,
        name=name,
        description=description,
        price=price,
        is_unlimited=is_unlimited,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def toggle_product(session: AsyncSession, product_id: int) -> bool:
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return False
    product.is_active = not product.is_active
    await session.commit()
    return product.is_active


async def delete_product(session: AsyncSession, product_id: int) -> bool:
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return False
    await session.execute(
        update(ProductItem).where(ProductItem.product_id == product_id).values(is_sold=True)
    )
    product.is_active = False
    product.name = f"[УДАЛЁН] {product.name}"
    await session.commit()
    return True


async def delete_category(session: AsyncSession, category_id: int) -> bool:
    result = await session.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return False
    await session.execute(
        update(Product).where(Product.category_id == category_id).values(is_active=False)
    )
    cat.is_active = False
    cat.name = f"[УДАЛЁН] {cat.name}"
    await session.commit()
    return True


async def update_product_price(session: AsyncSession, product_id: int, price: Decimal) -> bool:
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return False
    product.price = price
    await session.commit()
    return True


async def set_product_discount(
    session: AsyncSession,
    product_id: int,
    percent: Decimal | None,
    expires_at: datetime | None,
) -> bool:
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return False
    product.discount_percent = percent
    product.discount_expires_at = expires_at
    await session.commit()
    return True


async def add_product_keys(session: AsyncSession, product_id: int, keys: list[str]) -> int:
    count = 0
    for key in keys:
        key = key.strip()
        if key:
            item = ProductItem(product_id=product_id, data=key)
            session.add(item)
            count += 1
    await session.commit()
    return count


async def get_stock_for_product(session: AsyncSession, product_id: int) -> dict:
    total = (await session.execute(
        select(func.count(ProductItem.id)).where(ProductItem.product_id == product_id)
    )).scalar() or 0
    available = (await session.execute(
        select(func.count(ProductItem.id)).where(
            ProductItem.product_id == product_id,
            ProductItem.is_sold == False,
            ProductItem.is_reserved == False,
        )
    )).scalar() or 0
    sold = (await session.execute(
        select(func.count(ProductItem.id)).where(
            ProductItem.product_id == product_id,
            ProductItem.is_sold == True,
        )
    )).scalar() or 0
    return {"total": total, "available": available, "sold": sold}


async def get_orders_paginated(session: AsyncSession, offset: int = 0, limit: int = 10) -> list[Order]:
    result = await session.execute(
        select(Order).order_by(Order.created_at.desc()).offset(offset).limit(limit)
    )
    return result.scalars().all()


async def get_users_paginated(session: AsyncSession, offset: int = 0, limit: int = 10) -> list[User]:
    result = await session.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    return result.scalars().all()


async def toggle_user_ban(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return False
    user.is_banned = not user.is_banned
    await session.commit()
    return user.is_banned


async def get_all_promos(session: AsyncSession) -> list[PromoCode]:
    result = await session.execute(
        select(PromoCode).order_by(PromoCode.created_at.desc())
    )
    return result.scalars().all()


async def create_promo(
    session: AsyncSession,
    code: str,
    discount_type: str,
    discount_value: Decimal,
    max_uses: int | None = None,
) -> PromoCode:
    promo = PromoCode(
        code=code.upper(),
        discount_type=discount_type,
        discount_value=discount_value,
        max_uses=max_uses,
    )
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    return promo


async def toggle_promo(session: AsyncSession, promo_id: int) -> bool:
    result = await session.execute(select(PromoCode).where(PromoCode.id == promo_id))
    promo = result.scalar_one_or_none()
    if not promo:
        return False
    promo.is_active = not promo.is_active
    await session.commit()
    return promo.is_active


async def log_action(
    session: AsyncSession,
    admin_id: int,
    action: str,
    entity_type: str = None,
    entity_id: int = None,
    details: dict = None,
) -> None:
    log = AuditLog(
        admin_id=admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    session.add(log)
    await session.commit()
