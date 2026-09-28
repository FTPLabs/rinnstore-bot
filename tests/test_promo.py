import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.models import Base, Product, PromoCode, User
from bot.services.order_service import create_order


def test_promo_code_is_applied_to_order() -> None:
    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add_all([
                User(id=1, first_name="Buyer", referral_code="PROMOUSER"),
                PromoCode(code="SAVE10", discount_type="percent", discount_value=Decimal("10")),
            ])
            product = Product(name="Product", price=Decimal("100.00"), is_active=True)
            session.add(product)
            await session.flush()
            order = await create_order(
                session, 1,
                [{"product_id": product.id, "qty": 1, "price": Decimal("100.00")}],
                promo_code="save10",
            )
            assert order.total_amount == Decimal("90.00")
            promo = (await session.execute(select(PromoCode))).scalar_one()
            assert promo.used_count == 1
        await engine.dispose()

    asyncio.run(scenario())
