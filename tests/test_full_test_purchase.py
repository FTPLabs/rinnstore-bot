from bot.handlers.admin.full_test_purchase import PROVIDERS, TEST_NOTE, _provider_label
from bot.keyboards.admin import admin_main_kb


def test_admin_menu_contains_full_test_purchase() -> None:
    callbacks = [
        button.callback_data
        for row in admin_main_kb().inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "admin_full_test_purchase" in callbacks


def test_full_test_purchase_supports_all_simulated_providers() -> None:
    assert TEST_NOTE == "admin_full_test_purchase"
    assert {provider for provider, _ in PROVIDERS} == {
        "freekassa", "cryptobot", "rollypay", "telegram_stars", "balance", "manual",
    }
    assert _provider_label("freekassa") == "FreeKassa"
    assert _provider_label("telegram_stars") == "Telegram Stars"
