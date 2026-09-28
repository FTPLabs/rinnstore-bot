from bot.handlers.admin.full_test_purchase import TEST_NOTE, TEST_PRICE, TEST_PROVIDER
from bot.keyboards.admin import admin_main_kb


def test_admin_menu_has_only_full_test_purchase_entry() -> None:
    callbacks = [
        button.callback_data
        for row in admin_main_kb().inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "admin_full_test_purchase" in callbacks
    assert "admin_test_payment" not in callbacks


def test_fake_purchase_is_local_and_hidden() -> None:
    assert TEST_NOTE == "admin_full_test_purchase_fake_product"
    assert TEST_PROVIDER == "test_simulation"
    assert str(TEST_PRICE) == "1.00"
