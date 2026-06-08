from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..models import Category, Product, ProductItem

UNLIMITED_STOCK = 9999


async def get_root_categories(session: AsyncSession) -> list[Category]:
    """Возвращает активные корневые категории (без родителя)."""
    result = await session.execute(
        select(Category)
        .where(Category.is_active == True, Category.parent_id == None)
        .order_by(Category.sort_order, Category.name)
    )
    return result.scalars().all()


async def get_active_categories(session: AsyncSession) -> list[Category]:
    """Алиас get_root_categories для обратной совместимости."""
    return await get_root_categories(session)


async def get_subcategories(session: AsyncSession, parent_id: int) -> list[Category]:
    """Возвращает активные подкатегории указанной категории."""
    result = await session.execute(
        select(Category)
        .where(Category.is_active == True, Category.parent_id == parent_id)
        .order_by(Category.sort_order, Category.name)
    )
    return result.scalars().all()


async def has_subcategories(session: AsyncSession, category_id: int) -> bool:
    """Проверяет, есть ли у категории активные подкатегории."""
    result = await session.execute(
        select(func.count(Category.id))
        .where(Category.parent_id == category_id, Category.is_active == True)
    )
    return (result.scalar() or 0) > 0


async def get_category(session: AsyncSession, cat_id: int) -> Category | None:
    result = await session.execute(select(Category).where(Category.id == cat_id))
    return result.scalar_one_or_none()


async def get_products_in_category(session: AsyncSession, category_id: int) -> list[Product]:
    result = await session.execute(
        select(Product)
        .where(Product.category_id == category_id, Product.is_active == True)
        .order_by(Product.sort_order, Product.name)
    )
    return result.scalars().all()


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    result = await session.execute(select(Product).where(Product.id == product_id))
    return result.scalar_one_or_none()


async def get_stock_count(session: AsyncSession, product_id: int) -> int:
    product = await get_product(session, product_id)
    if product and product.is_unlimited:
        # FIX: считаем только непроданные items — после фикса deliver_order
        # безлимитные ключи тоже помечаются is_sold=True, поэтому старый
        # подсчёт (все items без фильтра) всегда возвращал UNLIMITED_STOCK
        # даже когда все ключи уже выданы
        item_result = await session.execute(
            select(func.count(ProductItem.id))
            .where(
                ProductItem.product_id == product_id,
                ProductItem.is_sold == False,
            )
        )
        if (item_result.scalar() or 0) > 0:
            return UNLIMITED_STOCK
        return 0

    result = await session.execute(
        select(func.count(ProductItem.id))
        .where(
            ProductItem.product_id == product_id,
            ProductItem.is_sold == False,
            ProductItem.is_reserved == False,
        )
    )
    return result.scalar() or 0


async def get_product_category_id(session: AsyncSession, product_id: int) -> int | None:
    result = await session.execute(
        select(Product.category_id).where(Product.id == product_id)
    )
    return result.scalar_one_or_none()
