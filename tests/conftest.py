"""Shared pytest configuration for the WLED Backup Service tests."""

from collections.abc import Generator

import pytest
import pytest_socket

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    _enable_custom_integrations: None,
) -> Generator[None, None, None]:
    """Enable loading this custom integration in the HA test harness."""
    yield


@pytest.hookimpl(trylast=True)
def pytest_runtest_setup() -> None:
    """Re-enable sockets after the HA plugin disables them during bootstrap tests."""
    pytest_socket.enable_socket()
