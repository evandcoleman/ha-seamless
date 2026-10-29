"""Permanent guard: every fixture is hand-written synthetic data, never real captures."""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED = {
    "auth_refresh.json",
    "orders_active.json",
    "orders_idle.json",
    "orders_stale.json",
    "orders_empty.json",
    "status_out_for_delivery.json",
    "status_out_for_delivery_moved.json",
    "status_delivered.json",
    "status_minimal.json",
    "status_unknown_state.json",
}
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE
)
SYNTHETIC_UUID_RE = re.compile(r"^00000000-0000-4000-8000-0000000000[0-9a-f]{2}$")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+")
URL_RE = re.compile(r"https?://[^\s\"']+")
TIMES_SQUARE = (40.7580, -73.9855)
MAX_COORD_DRIFT = 0.01


def _walk(node, key: str | None = None) -> Iterator[tuple[str | None, object]]:
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, k)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item, key)
    else:
        yield key, node


def _leaves() -> Iterator[tuple[str, str | None, object]]:
    for path in sorted(FIXTURES.glob("*.json")):
        for key, value in _walk(json.loads(path.read_text())):
            yield path.name, key, value


def _strings() -> list[tuple[str, str | None, str]]:
    return [(f, k, v) for f, k, v in _leaves() if isinstance(v, str)]


def test_expected_fixtures_exist() -> None:
    assert {p.name for p in FIXTURES.glob("*.json")} == EXPECTED


def test_every_uuid_is_synthetic() -> None:
    for name, key, value in _strings():
        for match in UUID_RE.findall(value):
            assert SYNTHETIC_UUID_RE.match(match), (name, key)


def test_every_email_is_example_com() -> None:
    for name, key, value in _strings():
        for match in EMAIL_RE.findall(value):
            assert match.endswith("@example.com"), (name, key)


def test_every_coordinate_is_near_times_square() -> None:
    lat, lon = TIMES_SQUARE
    coords = [
        (name, key, value)
        for name, key, value in _leaves()
        if key in {"latitude", "longitude"}
    ]
    assert coords, "fixtures should contain coordinates"
    for name, key, value in coords:
        centre = lat if key == "latitude" else lon
        assert abs(value - centre) <= MAX_COORD_DRIFT, (name, key)


def test_every_token_value_is_marked_test() -> None:
    tokens = [(n, k, v) for n, k, v in _strings() if k and "token" in k]
    assert tokens, "fixtures should contain tokens"
    for name, key, value in tokens:
        assert value.startswith("test-"), (name, key)


def test_every_url_host_is_example_com() -> None:
    for name, key, value in _strings():
        for url in URL_RE.findall(value):
            assert urlparse(url).hostname == "example.com", (name, key)
