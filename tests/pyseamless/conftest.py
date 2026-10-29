import asyncio

import pytest


class FakeClock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def session(aioclient_mock):
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    yield session
    await session.close()


@pytest.fixture
def calls(aioclient_mock):
    """Recorded requests as (method, url, body, headers)."""
    return lambda: [
        (method, str(url), data, headers)
        for method, url, data, headers in aioclient_mock.mock_calls
    ]


@pytest.fixture
def respond_in_sequence(aioclient_mock):
    """Register one URL that answers (status, json) pairs in order; the last repeats."""
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMockResponse,
    )

    def register(method: str, url: str, *responses: tuple[int, dict]) -> None:
        queue = list(responses)

        async def side_effect(request_method, request_url, data):
            status, body = queue.pop(0) if len(queue) > 1 else queue[0]
            return AiohttpClientMockResponse(
                request_method, request_url, status=status, json=body
            )

        getattr(aioclient_mock, method)(url, side_effect=side_effect)

    return register
