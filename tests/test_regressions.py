import asyncio
import hashlib
import hmac
from decimal import Decimal
from types import SimpleNamespace

from aiogram.types import MessageEntity
from aiogram.utils.text_decorations import html_decoration
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.handlers.catalog import _product_kb
from bot.keyboards.review import comment_kb, rating_kb
from bot.models import Base, Order, OrderItem, Product, ProductItem, Review, User
from bot.services.freekassa_service import freekassa_api_signature
from bot.services.order_service import (
    create_review_after_delivery_notification,
    deliver_order,
)
from bot.utils.delivery import format_delivered_items
from bot.utils.product_description import (
    product_description_from_message,
    product_description_to_html,
)


def test_product_description_preserves_telegram_custom_emoji() -> None:
    html_text = html_decoration.unparse(
        "⭐",
        [MessageEntity(type="custom_emoji", offset=0, length=1, custom_emoji_id="123456")],
    )
    message = SimpleNamespace(text="⭐", html_text=html_text)

    saved = product_description_from_message(message)

    assert saved.startswith("telegram-html:v1:")
    assert product_description_to_html(saved) == '<tg-emoji emoji-id="123456">⭐</tg-emoji>'
    assert product_description_to_html("<untrusted>") == "&lt;untrusted&gt;"


def test_review_keyboards_do_not_offer_a_second_purchase() -> None:
    for markup in (rating_kb(7), comment_kb(7)):
        labels = [button.text for row in markup.inline_keyboard for button in row]
        assert "Купить свой ключ" not in labels


def test_product_buy_button_has_purchase_icon_and_valid_callback() -> None:
    markup = _product_kb(product_id=42, stock=1, qty=1, user="ru")
    buy_button = markup.inline_keyboard[0][0]
    back_button = markup.inline_keyboard[1][0]

    assert buy_button.callback_data == "buy_42_1"
    assert buy_button.icon_custom_emoji_id == "5893473283696759404"
    assert buy_button.style == "primary"
    assert back_button.icon_custom_emoji_id == "5893333516871012690"


def test_delivered_key_html_is_escaped() -> None:
    text = format_delivered_items([{"data": "<key>&value"}])
    assert "<code>&lt;key&gt;&amp;value</code>" in text


def test_freekassa_signature_follows_alphabetical_value_order() -> None:
    data = {"currency": "RUB", "shopId": 777, "amount": "100.00", "nonce": 123}
    expected_source = "100.00|RUB|123|777"
    expected = hmac.new(b"api-key", expected_source.encode(), hashlib.sha256).hexdigest()
    assert freekassa_api_signature(data, "api-key") == expected


def test_review_is_created_only_after_key_message_confirmation() -> None:
    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with sessions() as session:
            user = User(
                id=1,
                first_name="Buyer",
                referral_code="BUYER1",
                terms_accepted=True,
                captcha_passed=True,
            )
            product = Product(name="Product", price=Decimal("100.00"), is_active=True)
            session.add_all([user, product])
            await session.flush()
            item = ProductItem(product_id=product.id, data="secret-key")
            order = Order(user_id=user.id, status="paid", total_amount=Decimal("100.00"))
            session.add_all([item, order])
            await session.flush()
            session.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=1,
                unit_price=Decimal("100.00"),
            ))
            await session.commit()

            delivered = await deliver_order(session, order.id)
            assert delivered == [{"data": "secret-key", "product_item_id": item.id}]
            assert (await session.execute(select(Review))).scalars().all() == []

            assert await create_review_after_delivery_notification(session, order.id)
            reviews = (await session.execute(select(Review))).scalars().all()
            assert len(reviews) == 1
            assert reviews[0].order_id == order.id

        await engine.dispose()

    asyncio.run(scenario())
