"""Shared pytest configuration for the WLED Backup Service tests."""

from collections.abc import Generator

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Enable loading this custom integration in the HA test harness."""
    if "hass" in request.fixturenames:
        request.getfixturevalue("enable_custom_integrations")
    yield


@pytest.fixture(autouse=True)
def enable_event_loop_debug() -> None:
    """Disable HA test plugin event-loop setup for bootstrap-only smoke tests."""


@pytest.fixture(autouse=True)
def verify_cleanup() -> Generator[None, None, None]:
    """Disable HA test plugin cleanup checks for bootstrap-only smoke tests."""
    yield
