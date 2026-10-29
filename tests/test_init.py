from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration


async def test_integration_loads(hass: HomeAssistant) -> None:
    integration = await async_get_integration(hass, "seamless")
    assert integration.domain == "seamless"
    assert integration.config_flow is True
