import json

from homeassistant.components.diagnostics import REDACTED

from custom_components.seamless.diagnostics import async_get_config_entry_diagnostics

from .helpers import setup_entry


async def test_diagnostics_redact_every_sensitive_field(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    entry = await setup_entry(hass, freezer)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    data = diag["entry"]["data"]
    assert data == {
        "ud_id": REDACTED,
        "client_id": REDACTED,
        "device_id": REDACTED,
        "refresh_token": REDACTED,
    }
    status = diag["coordinator"]["status"]
    assert status["dropoff_pin"] == REDACTED
    assert status["courier"]["name"] == REDACTED
    assert status["courier"]["photo_url"] == REDACTED
    assert status["location"]["latitude"] == REDACTED
    assert status["location"]["longitude"] == REDACTED
    order = diag["coordinator"]["order"]
    assert order["id"] == REDACTED
    assert order["order_number"] == REDACTED
    assert order["restaurant_name"] == REDACTED
    assert status["order_id"] == REDACTED
    # Non-sensitive operational state stays readable.
    assert diag["coordinator"]["is_active"] is True
    assert status["tracking_state"] == "OUT_FOR_DELIVERY"


async def test_diagnostics_dump_contains_no_synthetic_secrets(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    entry = await setup_entry(hass, freezer)

    dump = json.dumps(await async_get_config_entry_diagnostics(hass, entry), default=str)

    for secret in (
        "test-refresh",
        "test-access",
        "beta_seamless_test",
        '"0000"',
        "Test Courier",
        "Test Kitchen",
        "TEST-0001",
        "example.com",
        "40.76",
        "73.98",
        "00000000-0000-4000-8000",
    ):
        assert secret not in dump, secret


async def test_diagnostics_without_an_order(hass, freezer, api) -> None:
    entry = await setup_entry(hass, freezer)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["coordinator"] == {"is_active": False, "order": None, "status": None}
