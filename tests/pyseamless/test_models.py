from datetime import UTC, datetime

import pytest

from custom_components.seamless.pyseamless.exceptions import (
    ApiError,
    AuthenticationError,
    SeamlessConnectionError,
    SeamlessError,
)
from custom_components.seamless.pyseamless.models import (
    AuthResult,
    OrderStatus,
    OrderSummary,
    TokenSet,
    parse_orders,
)

NOW = 1_800_000_000.0


def test_exception_hierarchy() -> None:
    assert issubclass(AuthenticationError, SeamlessError)
    assert issubclass(ApiError, SeamlessError)
    assert issubclass(SeamlessConnectionError, SeamlessError)
    assert ApiError(503).status == 503


def test_token_set_expiry_is_now_plus_remaining_secs(load_fixture) -> None:
    handle = load_fixture("auth_refresh.json")["session_handle"]
    tokens = TokenSet.from_session_handle(handle, NOW)
    assert tokens.access_token == "test-access-2"
    assert tokens.refresh_token == "test-refresh-2"
    assert tokens.expires_at == NOW + 3600


def test_token_set_rejects_missing_tokens() -> None:
    with pytest.raises(AuthenticationError):
        TokenSet.from_session_handle({"token_remaining_secs": 10}, NOW)


def test_auth_result_reads_ud_id_and_tokens(load_fixture) -> None:
    result = AuthResult.from_response(load_fixture("auth_refresh.json"), NOW)
    assert result.ud_id == "00000000-0000-4000-8000-000000000001"
    assert result.tokens.refresh_token == "test-refresh-2"


def test_auth_result_ud_id_is_optional(load_fixture) -> None:
    body = load_fixture("auth_refresh.json")
    del body["credential"]
    assert AuthResult.from_response(body, NOW).ud_id is None


def test_parse_orders_newest_first_and_utc(load_fixture) -> None:
    payload = load_fixture("orders_active.json")
    payload["results"].reverse()
    orders = parse_orders(payload)
    assert [o.order_number for o in orders] == ["TEST-0001", "TEST-0002"]
    newest = orders[0]
    assert newest == OrderSummary(
        id="00000000-0000-4000-8000-0000000000a1",
        order_number="TEST-0001",
        order_status="OUT_FOR_DELIVERY",
        time_placed=datetime(2026, 1, 15, 17, 30, tzinfo=UTC),
        restaurant_name="Test Kitchen",
        tracking_enabled=True,
    )
    assert orders[1].tracking_enabled is False


def test_parse_orders_empty_and_malformed() -> None:
    assert parse_orders({"results": []}) == []
    assert parse_orders({}) == []
    assert parse_orders({"results": "nope"}) == []
    assert parse_orders({"results": [{"order_number": "no id"}, 7]}) == []


def test_parse_orders_bad_datetime_sorts_last(load_fixture) -> None:
    payload = load_fixture("orders_active.json")
    payload["results"][0]["time_placed"] = "not a date"
    orders = parse_orders(payload)
    assert orders[0].order_number == "TEST-0002"
    assert orders[1].time_placed is None


def test_order_status_reads_every_field(load_fixture) -> None:
    status = OrderStatus.from_dict(load_fixture("status_out_for_delivery.json"))
    assert status.order_id == "00000000-0000-4000-8000-0000000000a1"
    assert status.tracking_state == "OUT_FOR_DELIVERY"
    assert status.eta == datetime(2026, 1, 15, 18, 20, tzinfo=UTC)
    assert status.eta_window_start == datetime(2026, 1, 15, 18, 10, tzinfo=UTC)
    assert status.eta_window_end == datetime(2026, 1, 15, 18, 30, tzinfo=UTC)
    assert status.eta_state == "ON_TIME"
    assert status.dropoff_pin == "0000"
    assert status.courier.name == "Test Courier"
    assert status.courier.vehicle_type == "car"
    assert status.courier.photo_url == "https://example.com/courier-1.jpg"
    assert status.location.latitude == 40.76
    assert status.location.longitude == -73.986
    assert status.location.bearing == 90.0
    assert status.location.timestamp == datetime(2026, 1, 15, 17, 59, 30, tzinfo=UTC)


def test_order_status_without_location(load_fixture) -> None:
    status = OrderStatus.from_dict(load_fixture("status_delivered.json"))
    assert status.tracking_state == "DELIVERED"
    assert status.location is None
    assert status.courier is not None


def test_minimal_order_status_is_all_none(load_fixture) -> None:
    status = OrderStatus.from_dict(load_fixture("status_minimal.json"))
    assert status.order_id == "00000000-0000-4000-8000-0000000000a1"
    for field in (
        "tracking_state",
        "eta",
        "eta_window_start",
        "eta_window_end",
        "eta_state",
        "courier",
        "location",
        "dropoff_pin",
    ):
        assert getattr(status, field) is None


def test_order_status_bad_values_become_none(load_fixture) -> None:
    body = load_fixture("status_out_for_delivery.json")
    body["display_estimate_range"]["start_time"] = "garbage"
    body["delivery_tracking_info"]["current_courier_location"]["latitude"] = "north"
    body["dropoff_pin_code"] = 1234
    body["delivery_tracking_info"]["courier"] = []
    status = OrderStatus.from_dict(body)
    assert status.eta_window_start is None
    assert status.eta is not None
    assert status.location is None
    assert status.dropoff_pin is None
    assert status.courier is None


def test_order_status_non_dict_is_empty() -> None:
    assert OrderStatus.from_dict([]).order_id is None
