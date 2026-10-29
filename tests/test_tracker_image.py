from unittest.mock import AsyncMock, patch

from homeassistant.components import image
from homeassistant.components.image import Image
from homeassistant.util import dt as dt_util

from custom_components.seamless.const import ACTIVE_INTERVAL

from .helpers import SECOND, setup_entry, tick

TRACKER = "device_tracker.seamless_courier"
PHOTO = "image.seamless_courier_photo"


async def test_no_order_tracker_is_not_home_without_coordinates(hass, freezer, api) -> None:
    await setup_entry(hass, freezer)

    tracker = hass.states.get(TRACKER)
    assert tracker.state == "not_home"
    assert "latitude" not in tracker.attributes
    assert "longitude" not in tracker.attributes
    assert hass.states.get(PHOTO).state == "unknown"


async def test_active_order_tracker_has_position_and_attributes(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    await setup_entry(hass, freezer)

    attrs = hass.states.get(TRACKER).attributes
    assert attrs["latitude"] == 40.76
    assert attrs["longitude"] == -73.986
    assert attrs["source_type"] == "gps"
    assert attrs["bearing"] == 90.0
    assert attrs["timestamp"] == "2026-01-15T17:59:30+00:00"


async def test_tracker_follows_the_courier(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    await setup_entry(hass, freezer)
    api.status = "status_out_for_delivery_moved.json"
    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)

    attrs = hass.states.get(TRACKER).attributes
    assert (attrs["latitude"], attrs["longitude"]) == (40.759, -73.987)
    assert attrs["bearing"] == 135.5


async def test_delivered_order_without_location_returns_to_not_home(
    hass, freezer, api
) -> None:
    api.orders = "orders_active.json"
    await setup_entry(hass, freezer)
    api.status = "status_delivered.json"
    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)

    tracker = hass.states.get(TRACKER)
    assert tracker.state == "not_home"
    assert "latitude" not in tracker.attributes


async def test_image_last_updated_changes_only_when_the_url_changes(
    hass, freezer, api
) -> None:
    api.orders = "orders_active.json"
    await setup_entry(hass, freezer)
    first = hass.states.get(PHOTO).state
    assert first == "2026-01-15T18:00:00+00:00"

    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)
    assert hass.states.get(PHOTO).state == first

    api.status = "status_out_for_delivery_moved.json"  # photo-2.jpg
    await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)
    assert hass.states.get(PHOTO).state == dt_util.utcnow().isoformat()
    assert hass.states.get(PHOTO).state != first


async def test_image_cache_is_cleared_when_the_url_changes(hass, freezer, api) -> None:
    api.orders = "orders_active.json"
    await setup_entry(hass, freezer)
    entity = hass.data[image.DATA_COMPONENT].get_entity(PHOTO)
    loader = AsyncMock(
        side_effect=lambda url: Image("image/jpeg", url.encode()),
    )
    with patch.object(type(entity), "_async_load_image_from_url", loader):
        assert await entity.async_image() == b"https://example.com/courier-1.jpg"
        assert await entity.async_image() == b"https://example.com/courier-1.jpg"
        assert loader.await_count == 1

        api.status = "status_out_for_delivery_moved.json"
        await tick(hass, freezer, ACTIVE_INTERVAL + SECOND)
        assert await entity.async_image() == b"https://example.com/courier-2.jpg"
        assert loader.await_count == 2
