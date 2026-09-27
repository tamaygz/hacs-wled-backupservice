"""Tests for config-entry diagnostics."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.wled_backupservice.diagnostics import (
    _mask_value,
    async_get_config_entry_diagnostics,
)
from custom_components.wled_backupservice.discovery import WLEDDevice
from custom_components.wled_backupservice.manager import INTEGRATION_VERSION, WLEDBackupManager
from custom_components.wled_backupservice.storage import (
    StoredBackup,
    StoredBackupDevice,
    StoredBackupFile,
)


class FakeEntry:
    """Minimal config-entry stand-in for diagnostics tests."""

    def __init__(self) -> None:
        self.domain = "wled_backupservice"
        self.entry_id = "entry-1"
        self.title = "WLED Backup Service"
        self.data = {"host": "10.0.0.10", "mac": "aabbccddeeff"}
        self.options = {"storage_root": "share", "subdir": "wled_backups"}
        self.runtime_data: object | None = None


def _make_manager() -> WLEDBackupManager:
    def _async_create_background_task(
        target: Any,
        name: str,
        eager_start: bool = False,
    ) -> asyncio.Task[Any]:
        del eager_start
        return asyncio.create_task(target, name=name)

    hass = SimpleNamespace(
        data={},
        config=SimpleNamespace(path=lambda *_parts: "config"),
        async_create_background_task=_async_create_background_task,
    )
    entry = SimpleNamespace(options={"schedule_enabled": False})
    return WLEDBackupManager(hass=hass, entry=entry)


@pytest.mark.asyncio
async def test_diagnostics_returns_redacted_metadata() -> None:
    entry = FakeEntry()
    manager = _make_manager()
    manager.is_setup = True
    manager.discovered_device_count = 1
    manager.last_backup_status = "success"
    manager.last_backup_success = datetime(2026, 9, 27, 4, 0, 0, tzinfo=UTC)
    manager.last_error = None
    async def _discover_devices(*args: Any, **kwargs: Any) -> list[WLEDDevice]:
        del args, kwargs
        return await asyncio.sleep(
        0,
        result=[
            WLEDDevice(
                device_id="wled-aabbccddeeff",
                name="Kitchen",
                host="10.0.0.10",
                mac="aabbccddeeff",
                ha_device_id="ha-device",
                ha_config_entry_id="wled-entry",
                firmware_version="0.16.0",
            )
        ],
        )

    async def _list_backups(*args: Any, **kwargs: Any) -> list[StoredBackup]:
        del args, kwargs
        return await asyncio.sleep(
        0,
        result=[
            StoredBackup(
                backup_id="kitchen/2026/09/27/040000",
                path=Path("C:/backups/kitchen/2026/09/27/040000"),
                created_at=datetime(2026, 9, 27, 4, 0, 0, tzinfo=UTC),
                integration_version=INTEGRATION_VERSION,
                device=StoredBackupDevice(
                    name="Kitchen",
                    host="10.0.0.10",
                    mac="aabbccddeeff",
                    device_id="wled-aabbccddeeff",
                    firmware_version="0.16.0",
                ),
                files=(StoredBackupFile(name="cfg.json", size=2, sha256="hash"),),
            )
        ],
        )

    manager.async_discover_devices = _discover_devices  # type: ignore[method-assign]
    manager.async_list_backups = _list_backups  # type: ignore[method-assign]
    entry.runtime_data = manager

    result = await async_get_config_entry_diagnostics(SimpleNamespace(), entry)

    assert result["integration"]["version"] == INTEGRATION_VERSION
    assert result["entry"]["data"]["host"] == "**REDACTED**"
    assert result["entry"]["data"]["mac"] == "**REDACTED**"
    assert result["runtime"]["last_backup_status"] == "success"
    assert result["devices"][0]["name"] == "Kitchen"
    assert result["devices"][0]["host_masked"] == "10***10"
    assert result["devices"][0]["mac_masked"] == "aa***ff"
    assert result["devices"][0]["backup_count"] == 1
    assert "files" not in result["backups"]["by_device"][0]


@pytest.mark.asyncio
async def test_diagnostics_handles_discovery_and_inventory_errors() -> None:
    entry = FakeEntry()
    manager = _make_manager()
    manager.last_backup_status = "failed"
    manager.last_error = "offline"

    async def _raise_discovery(*args: Any, **kwargs: Any) -> list[WLEDDevice]:
        del args, kwargs
        raise RuntimeError("discovery failed")

    async def _raise_inventory(*args: Any, **kwargs: Any) -> list[StoredBackup]:
        del args, kwargs
        raise RuntimeError("inventory failed")

    manager.async_discover_devices = _raise_discovery  # type: ignore[method-assign]
    manager.async_list_backups = _raise_inventory  # type: ignore[method-assign]
    entry.runtime_data = manager

    result = await async_get_config_entry_diagnostics(SimpleNamespace(), entry)

    assert result["discovery_error"] == "discovery failed"
    assert result["backup_inventory_error"] == "inventory failed"
    assert result["devices"] == []
    assert result["backups"]["total_count"] == 0
    assert result["runtime"]["last_error"] == "offline"


@pytest.mark.asyncio
async def test_diagnostics_handles_unloaded_entry() -> None:
    entry = FakeEntry()

    result = await async_get_config_entry_diagnostics(SimpleNamespace(), entry)

    assert result["runtime"]["loaded"] is False
    assert result["devices"] == []
    assert result["backups"]["total_count"] == 0


def test_mask_value_handles_empty_and_short_values() -> None:
    assert _mask_value(None) is None
    assert _mask_value("") == ""
    assert _mask_value("abcd") == "****"