import asyncio
import hashlib
import hmac
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from types import SimpleNamespace

from aiogram.types import MessageEntity
from aiogram.utils.text_decorations import html_decoration
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.handlers.catalog import _edit_message_text_or_caption, _product_kb
from bot.keyboards.review import comment_kb, rating_kb
from bot.main import _table_column_names
from bot.services.review_service import _send_moderation_notice
from bot.handlers.admin.settings_admin import _is_valid_telegram_chat_target, settings_main_kb
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


def test_purchase_updates_photo_caption_instead_of_missing_text() -> None:
    async def scenario() -> None:
        message = SimpleNamespace(
            photo=[object()],
            edit_caption=AsyncMock(),
            edit_text=AsyncMock(),
        )
        markup = object()

        await _edit_message_text_or_caption(message, "order summary", markup)

        message.edit_caption.assert_awaited_once_with(
            caption="order summary", reply_markup=markup, parse_mode="HTML"
        )
        message.edit_text.assert_not_awaited()

    asyncio.run(scenario())


def test_purchase_updates_text_for_text_only_message() -> None:
    async def scenario() -> None:
        message = SimpleNamespace(
            photo=[],
            edit_caption=AsyncMock(),
            edit_text=AsyncMock(),
        )
        markup = object()

        await _edit_message_text_or_caption(message, "order summary", markup)

        message.edit_text.assert_awaited_once_with(
            "order summary", reply_markup=markup, parse_mode="HTML"
        )
        message.edit_caption.assert_not_awaited()

    asyncio.run(scenario())


def test_schema_column_detection_uses_dialect_aware_inspector() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE reviews (id INTEGER PRIMARY KEY, status TEXT)"
            )
            assert _table_column_names(connection, "reviews") == {"id", "status"}
    finally:
        engine.dispose()


def test_review_moderation_routes_once_to_configured_group() -> None:
    async def scenario() -> None:
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=55)))
        with patch("bot.services.review_service.get_cached", return_value="-1001234567890"):
            sent_ids = await _send_moderation_notice(bot, "review", 7, [11, 22])

        assert sent_ids == [55]
        bot.send_message.assert_awaited_once()
        assert bot.send_message.await_args.args[0] == "-1001234567890"
        assert bot.send_message.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "review_approve_7"

    asyncio.run(scenario())


def test_review_moderation_falls_back_to_each_admin_dm() -> None:
    async def scenario() -> None:
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=[SimpleNamespace(message_id=10), SimpleNamespace(message_id=11)]))
        with patch("bot.services.review_service.get_cached", return_value=""):
            sent_ids = await _send_moderation_notice(bot, "review", 8, [11, 22])

        assert sent_ids == [10, 11]
        assert [entry.args[0] for entry in bot.send_message.await_args_list] == [11, 22]

    asyncio.run(scenario())


def test_review_chat_configuration_accepts_supported_targets_only() -> None:
    assert _is_valid_telegram_chat_target("@review_channel")
    assert _is_valid_telegram_chat_target("-1001234567890")
    assert not _is_valid_telegram_chat_target("https://t.me/review_channel")
    assert not _is_valid_telegram_chat_target("12345")
    callbacks = {
        button.callback_data
        for row in settings_main_kb().inline_keyboard
        for button in row
    }
    assert "set_review_channel" in callbacks
    assert "set_review_moderation_chat" in callbacks


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
