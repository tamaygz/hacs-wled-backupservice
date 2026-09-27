"""End-to-end integration tests for the WLED Backup Service."""

from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.wled_backupservice.discovery import WLEDDevice
from custom_components.wled_backupservice.manager import WLEDBackupManager
from custom_components.wled_backupservice.retention import PruneResult
from custom_components.wled_backupservice.wled_client import (
    WLEDClientCapabilities,
    WLEDInfo,
)


@dataclass
class FakeDiscoveryRuntime:
    """Discovery collaborator for end-to-end tests."""

    devices: list[WLEDDevice]

    async def async_discover_wled_devices(self, _hass: object) -> list[WLEDDevice]:
        return self.devices


class FakeRuntimeHass:
    """Minimal Home Assistant runtime for manager/storage integration tests."""

    def __init__(self, config_root: Path) -> None:
        config_root.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, object] = {}
        self.config = SimpleNamespace(path=lambda *_parts: str(config_root))

    async def async_add_executor_job(self, func: Any, *args: Any) -> Any:
        return func(*args)

    def async_create_background_task(
        self,
        target: Any,
        name: str,
        eager_start: bool = False,
    ) -> Any:
        del target, name, eager_start
        raise AssertionError("background tasks are not expected in this e2e test")


@dataclass
class FakeEntry:
    """Minimal config entry for manager end-to-end coverage."""

    options: dict[str, Any]

    def async_on_unload(self, callback: Any) -> None:
        del callback

    def async_create_background_task(
        self,
        hass: Any,
        target: Any,
        name: str,
        eager_start: bool = False,
    ) -> Any:
        return hass.async_create_background_task(target, name, eager_start)


class FakeRuntimeClient:
    """Mutable fake WLED client for end-to-end service calls."""

    def __init__(
        self,
        *,
        info_payload: dict[str, Any],
        cfg_payload: dict[str, Any],
        presets_payload: bytes,
        presets_supported: bool,
    ) -> None:
        self.capabilities = WLEDClientCapabilities(
            presets_upload_supported=presets_supported,
            presets_upload_verified=presets_supported,
        )
        product = info_payload.get("product")
        device_id = info_payload.get("deviceId")
        self._info = WLEDInfo(
            brand=str(info_payload["brand"]),
            product=str(product) if product is not None else None,
            name=str(info_payload["name"]),
            version=str(info_payload["ver"]),
            architecture=str(info_payload["arch"]),
            build_id=int(info_payload["vid"]),
            mac_address=str(info_payload["mac"]),
            device_id=str(device_id) if device_id is not None else None,
        )
        self._cfg = copy.deepcopy(cfg_payload)
        self._presets = presets_payload
        self._state = {"on": True, "bri": 128}
        self.reboot_count = 0

    async def async_get_info(self) -> WLEDInfo:
        return self._info

    async def async_get_config(self) -> dict[str, Any]:
        return copy.deepcopy(self._cfg)

    async def async_get_presets_raw(self) -> bytes:
        return self._presets

    async def async_get_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._state)

    async def async_set_config(self, config: dict[str, Any]) -> None:
        self._cfg = copy.deepcopy(config)

    async def async_upload_presets(self, payload: bytes) -> None:
        self._presets = payload

    async def async_reboot(self) -> None:
        self.reboot_count += 1


def test_manager_roundtrip_backup_list_restore_and_prune(
    tmp_path: Path,
    wled_fixture_payloads: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    socket_enabled: None,
) -> None:
    _ = socket_enabled
    caplog.set_level(logging.CRITICAL, logger="custom_components.wled_backupservice")

    async def scenario() -> None:
        hass = FakeRuntimeHass(tmp_path / "config-root")
        manager = WLEDBackupManager(
            hass=hass,
            entry=FakeEntry(
                {
                    "schedule_enabled": False,
                    "storage_root": "config",
                    "subdir": "e2e_wled_backups",
                    "include_presets": True,
                    "include_state": False,
                    "retention_count": 30,
                    "retention_days": 0,
                    "backup_before_restore": True,
                    "verify_after_restore": True,
                    "reboot_after_restore": False,
                }
            ),
        )
        await manager.async_setup()

        device = WLEDDevice(
            device_id="wled-aabbccddeeff",
            name="Kitchen Strip",
            host="10.0.0.10",
            mac="aabbccddeeff",
            ha_device_id="ha-device-one",
            ha_config_entry_id="wled-entry-one",
            firmware_version="0.16.0",
        )
        manager.discovery = FakeDiscoveryRuntime([device])
        client = FakeRuntimeClient(
            info_payload=wled_fixture_payloads["info"],
            cfg_payload=wled_fixture_payloads["cfg"],
            presets_payload=wled_fixture_payloads["presets"],
            presets_supported=False,
        )
        manager.client_factory = lambda _host: client

        backup_results = await manager.async_backup_all()
        assert len(backup_results) == 1
        backup_id = backup_results[0].backup_id
        assert backup_id is not None
        backup_path = backup_results[0].path
        assert backup_path is not None
        assert backup_path.is_dir()
        assert (backup_path / "manifest.json").exists()

        listed_backups = await manager.async_list_backups(limit=1)
        assert listed_backups[0].backup_id == backup_id
        assert listed_backups[0].device.name == "Kitchen Strip"

        client._cfg = {"wifi": {"hostname": "modified-host"}}
        restore_result = await manager.async_restore(
            device,
            backup_id=backup_id,
            backup_before_restore=False,
            restore_presets=True,
        )
        assert restore_result.config_status == "ok"
        assert restore_result.presets_status == "unsupported"
        assert restore_result.success is True

        prune_result = await manager.async_prune(dry_run=True)
        assert isinstance(prune_result, PruneResult)
        assert prune_result.dry_run is True
        assert prune_result.device_results[0].device_id == "wled-aabbccddeeff"

        await manager.async_shutdown()

    asyncio.run(scenario())