"""Tests for the integration lifecycle scaffold."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import custom_components.wled_backupservice as integration
from custom_components.wled_backupservice.manager import WLEDBackupManager
from custom_components.wled_backupservice.services import SERVICES_REGISTERED_KEY


class FakeEntry:
    """Minimal config-entry stand-in for lifecycle tests."""

    def __init__(self, entry_id: str = "test-entry") -> None:
        self.entry_id = entry_id
        self.runtime_data = None
        self.update_listeners: list = []
        self.unload_callbacks: list = []

    def add_update_listener(self, listener: Callable[..., Any]) -> Callable[[], None]:
        self.update_listeners.append(listener)

        def remove_listener() -> None:
            if listener in self.update_listeners:
                self.update_listeners.remove(listener)

        return remove_listener

    def async_on_unload(self, callback: Callable[[], None]) -> None:
        self.unload_callbacks.append(callback)


def test_async_setup_entry_sets_runtime_data(socket_enabled: None) -> None:
    """Setting up an entry should attach a manager to runtime_data."""
    _ = socket_enabled
    hass = SimpleNamespace(data={})
    entry = FakeEntry()

    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True
    assert isinstance(entry.runtime_data, WLEDBackupManager)
    assert entry.runtime_data.is_setup is True
    assert len(entry.update_listeners) == 1
    assert len(entry.unload_callbacks) == 1


def test_async_unload_entry_calls_manager_shutdown(socket_enabled: None) -> None:
    """Unloading an entry should call manager shutdown."""
    _ = socket_enabled
    hass = SimpleNamespace(data={})
    entry = FakeEntry()
    asyncio.run(integration.async_setup_entry(hass, entry))
    manager = entry.runtime_data

    with patch.object(manager, "async_shutdown", new=AsyncMock()) as shutdown_mock:
        assert asyncio.run(integration.async_unload_entry(hass, entry)) is True

    shutdown_mock.assert_awaited_once()


def test_async_setup_registers_services_idempotently(socket_enabled: None) -> None:
    """Domain setup should register services only once."""
    _ = socket_enabled
    hass = SimpleNamespace(data={})

    assert asyncio.run(integration.async_setup(hass, {})) is True
    assert hass.data[SERVICES_REGISTERED_KEY] is True

    assert asyncio.run(integration.async_setup(hass, {})) is True
    assert hass.data[SERVICES_REGISTERED_KEY] is True


def test_update_listener_reloads_entry(socket_enabled: None) -> None:
    """The update listener should request a config entry reload."""
    _ = socket_enabled
    reload_mock = AsyncMock()
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_reload=reload_mock))
    entry = FakeEntry(entry_id="reload-me")

    asyncio.run(integration._async_update_listener(hass, entry))

    reload_mock.assert_awaited_once_with(entry.entry_id)