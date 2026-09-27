"""Shared pytest configuration for the WLED Backup Service tests."""

import asyncio
import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from homeassistant import loader
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wled_backupservice.const import (
    CONF_BACKUP_BEFORE_RESTORE,
    CONF_CREATE_ARCHIVE,
    CONF_DAILY_TIME,
    CONF_INCLUDE_PRESETS,
    CONF_INCLUDE_STATE,
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    CONF_REBOOT_AFTER_RESTORE,
    CONF_RETENTION_COUNT,
    CONF_RETENTION_DAYS,
    CONF_SCHEDULE_ENABLED,
    CONF_STORAGE_ROOT,
    CONF_SUBDIR,
    CONF_VERIFY_AFTER_RESTORE,
    DEFAULT_BACKUP_BEFORE_RESTORE,
    DEFAULT_CREATE_ARCHIVE,
    DEFAULT_DAILY_TIME,
    DEFAULT_INCLUDE_PRESETS,
    DEFAULT_INCLUDE_STATE,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
    DEFAULT_REBOOT_AFTER_RESTORE,
    DEFAULT_RETENTION_COUNT,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_VERIFY_AFTER_RESTORE,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


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


@pytest.fixture(scope="session")
def wled_fixture_bytes() -> dict[str, bytes]:
    """Load realistic WLED fixture payloads once per test session."""
    return {
        name: (FIXTURES_DIR / name).read_bytes()
        for name in ("info.json", "cfg.json", "presets.json")
    }


@pytest.fixture(scope="session")
def wled_fixture_payloads(wled_fixture_bytes: dict[str, bytes]) -> dict[str, Any]:
    """Return parsed JSON payloads alongside the raw presets bytes."""
    return {
        "info": json.loads(wled_fixture_bytes["info.json"].decode("utf-8")),
        "cfg": json.loads(wled_fixture_bytes["cfg.json"].decode("utf-8")),
        "presets": wled_fixture_bytes["presets.json"],
    }


@pytest.fixture
def default_integration_options(tmp_path: Path) -> dict[str, Any]:
    """Build default config-entry options rooted in the pytest temp config dir."""
    return {
        CONF_SCHEDULE_ENABLED: False,
        CONF_INTERVAL: DEFAULT_INTERVAL,
        CONF_INTERVAL_UNIT: DEFAULT_INTERVAL_UNIT,
        CONF_DAILY_TIME: DEFAULT_DAILY_TIME,
        CONF_STORAGE_ROOT: "config",
        CONF_SUBDIR: "e2e_wled_backups",
        CONF_INCLUDE_PRESETS: DEFAULT_INCLUDE_PRESETS,
        CONF_INCLUDE_STATE: DEFAULT_INCLUDE_STATE,
        CONF_CREATE_ARCHIVE: DEFAULT_CREATE_ARCHIVE,
        CONF_RETENTION_COUNT: DEFAULT_RETENTION_COUNT,
        CONF_RETENTION_DAYS: DEFAULT_RETENTION_DAYS,
        CONF_BACKUP_BEFORE_RESTORE: DEFAULT_BACKUP_BEFORE_RESTORE,
        CONF_VERIFY_AFTER_RESTORE: DEFAULT_VERIFY_AFTER_RESTORE,
        CONF_REBOOT_AFTER_RESTORE: DEFAULT_REBOOT_AFTER_RESTORE,
    }


@pytest.fixture
def integration_entry(default_integration_options: dict[str, Any]) -> MockConfigEntry:
    """Return a configured MockConfigEntry for the integration."""
    return MockConfigEntry(domain=DOMAIN, data={}, options=default_integration_options)
