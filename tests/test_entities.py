import pytest

from custom_components.seamless.const import IDLE_INTERVAL

from .helpers import SECOND, setup_entry, tick

STATUS_SENSORS = {
    "sensor.seamless_order_status": "out_for_delivery",
    "sensor.seamless_eta": "2026-01-15T18:20:00+00:00",
    "sensor.seamless_eta_window_start": "2026-01-15T18:10:00+00:00",
    "sensor.seamless_eta_window_end": "2026-01-15T18:30:00+00:00",
    "sensor.seamless_eta_state": "on_time",
    "sensor.seamless_courier": "Test Courier",
    "sensor.seamless_dropoff_pin": "0000",
}
ALL_SENSORS = {**STATUS_SENSORS, "sensor.seamless_restaurant": "Test Kitchen"}


async def test_no_order_binary_sensor_off_and_sensors_unknown(hass, freezer, api) -> None:
    await setup_entry(hass, freezer)

    assert hass.states.get("binary_sensor.seamless_order_active").state == "off"
    for entity_id in ALL_SENSORS:
        assert hass.states.get(entity_id).state == "unknown", entity_id


async def test_active_order_values(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    await setup_entry(hass, freezer)

    for entity_id, expected in ALL_SENSORS.items():
        assert hass.states.get(entity_id).state == expected, entity_id
    active = hass.states.get("binary_sensor.seamless_order_active")
    assert active.state == "on"
    assert active.attributes["order_id"] == "00000000-0000-4000-8000-0000000000a1"
    assert active.attributes["order_number"] == "TEST-0001"
    assert hass.states.get("sensor.seamless_courier").attributes["vehicle_type"] == "car"


async def test_delivered_order_keeps_status_but_is_not_active(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    await setup_entry(hass, freezer)
    api.status = "status_delivered.json"
    await tick(hass, freezer, IDLE_INTERVAL + SECOND)

    assert hass.states.get("binary_sensor.seamless_order_active").state == "off"
    assert hass.states.get("sensor.seamless_order_status").state == "delivered"


async def test_unknown_tracking_state_is_passed_through(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    api.status = "status_unknown_state.json"
    await setup_entry(hass, freezer)

    state = hass.states.get("sensor.seamless_order_status")
    assert state.state == "teleporting"
    assert "teleporting" in state.attributes["options"]


async def test_minimal_status_gives_unknown(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    api.status = "status_minimal.json"
    await setup_entry(hass, freezer)

    for entity_id in STATUS_SENSORS:
        assert hass.states.get(entity_id).state == "unknown", entity_id
    assert hass.states.get("sensor.seamless_restaurant").state == "Test Kitchen"


@pytest.mark.parametrize(
    "entity_id",
    [*ALL_SENSORS, "binary_sensor.seamless_order_active"],
)
async def test_coordinator_failure_makes_entities_unavailable(
    hass, freezer, api, entity_id
) -> None:
    await setup_entry(hass, freezer)
    api.orders_http = 500
    await tick(hass, freezer, IDLE_INTERVAL + SECOND)

    assert hass.states.get(entity_id).state == "unavailable"


async def test_all_entities_belong_to_one_seamless_device(hass, freezer, api) -> None:
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    entry = await setup_entry(hass, freezer)
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entities) == 11
    assert {e.device_id for e in entities} == {next(iter(dr.async_get(hass).devices)).id}
    assert all(e.unique_id.startswith(f"{entry.unique_id}_") for e in entities)
    device = dr.async_get(hass).async_get(entities[0].device_id)
    assert device.name == "Seamless"
