"""Shared pytest configuration for the WLED Backup Service tests."""

import asyncio
from collections.abc import Generator

import pytest
from homeassistant import loader
from homeassistant.core import HomeAssistant

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def enable_event_loop_debug() -> None:
    """Disable HA test plugin event-loop setup for bootstrap-only smoke tests."""


@pytest.fixture(autouse=True)
def verify_cleanup() -> Generator[None, None, None]:
    """Disable HA test plugin cleanup checks for bootstrap-only smoke tests."""
    yield


@pytest.fixture
def enable_custom_integrations(hass: HomeAssistant) -> None:
    """Refresh custom integration discovery for tests in this repository."""
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)


@pytest.fixture
def event_loop(
    socket_enabled: None,
) -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop with sockets temporarily enabled for Windows HA tests."""
    _ = socket_enabled
    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)
