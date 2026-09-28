from decimal import Decimal

from bot.handlers.admin.test_payment_admin import TEST_AMOUNT, TEST_NOTE, _payment_kb
from bot.keyboards.admin import admin_main_kb


def test_admin_menu_contains_test_payment_button() -> None:
    labels = [
        button.text
        for row in admin_main_kb().inline_keyboard
        for button in row
    ]
    assert "₽ Тестовый платёж 1 ₽" in labels


def test_test_payment_is_fixed_to_one_ruble() -> None:
    assert TEST_AMOUNT == Decimal("1.00")
    assert TEST_NOTE == "admin_freekassa_test_payment"


def test_test_payment_keyboard_uses_admin_check_callback() -> None:
    markup = _payment_kb("https://pay.example/1", 42)
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "admin_test_check_42" in callbacks
    assert "check_payment_42_freekassa" not in callbacks
