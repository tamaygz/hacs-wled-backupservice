"""Tests for service registration and action handlers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.wled_backupservice as integration
import custom_components.wled_backupservice.services as services_module
from custom_components.wled_backupservice.const import DOMAIN
from custom_components.wled_backupservice.discovery import WLEDDevice
from custom_components.wled_backupservice.exceptions import WLEDValidationError
from custom_components.wled_backupservice.models import BackupResult
from custom_components.wled_backupservice.retention import (
    DevicePruneResult,
    PruneResult,
)
from custom_components.wled_backupservice.storage import (
    StoredBackup,
    StoredBackupDevice,
    StoredBackupFile,
)


@dataclass
class FakeManager:
    """Minimal runtime_data stand-in for service tests."""

    backup_result: BackupResult
    backup_all_results: list[BackupResult]
    backups: list[StoredBackup]
    prune_result: PruneResult
    devices: list[WLEDDevice]

    def __post_init__(self) -> None:
        self.restore_calls: list[dict[str, object]] = []
        self.delete_calls: list[str] = []
        self.prune_calls: list[dict[str, object]] = []
        self.restore_response: dict[str, object] | None = None

    async def async_backup_device(
        self,
        device: WLEDDevice,
        **kwargs: object,
    ) -> BackupResult:
        return self.backup_result

    async def async_backup_all(self, **kwargs: object) -> list[BackupResult]:
        return self.backup_all_results

    async def async_restore(
        self,
        device: WLEDDevice,
        **kwargs: object,
    ) -> dict[str, object]:
        self.restore_calls.append({"device": device, **kwargs})
        if self.restore_response is None:
            raise NotImplementedError
        return self.restore_response

    async def async_list_backups(self, **kwargs: object) -> list[StoredBackup]:
        device = kwargs.get("device")
        limit = kwargs.get("limit")
        results = self.backups
        if isinstance(device, WLEDDevice):
            results = [
                backup
                for backup in results
                if backup.device.device_id == device.device_id
            ]
        if isinstance(limit, int):
            results = results[:limit]
        return results

    async def async_delete_backup(self, *, backup_id: str) -> None:
        self.delete_calls.append(backup_id)

    async def async_prune(self, **kwargs: object) -> PruneResult:
        self.prune_calls.append(kwargs)
        device = kwargs.get("device")
        if isinstance(device, WLEDDevice):
            return PruneResult(
                dry_run=bool(kwargs.get("dry_run", False)),
                device_results=(
                    DevicePruneResult(
                        device_id=device.device_id,
                        total_backups=1,
                        kept_backup_ids=(f"{device.device_id}/keep",),
                        would_delete_backup_ids=(f"{device.device_id}/drop",),
                        deleted_backup_ids=(),
                        failed_backup_ids=(),
                    ),
                ),
            )
        return self.prune_result

    async def async_discover_devices(self) -> list[WLEDDevice]:
        return self.devices


def _make_device(
    *,
    device_id: str = "device-one",
    name: str = "Kitchen",
    host: str = "10.0.0.10",
) -> WLEDDevice:
    return WLEDDevice(
        device_id=device_id,
        name=name,
        host=host,
        mac=device_id,
        ha_device_id=f"ha-{device_id}",
        ha_config_entry_id=f"entry-{device_id}",
        firmware_version="0.16.0",
    )


def _make_backup_result(device_id: str = "device-one") -> BackupResult:
    return BackupResult(
        device_id=device_id,
        device_name="Kitchen",
        success=True,
        backup_id="device-one/2026/09/27/030000",
        path=Path("C:/backups/device-one/2026/09/27/030000"),
        files=("cfg.json", "info.json"),
        created_at=datetime(2026, 9, 27, 3, 0, 0, tzinfo=UTC),
        error=None,
    )


def _make_stored_backup(device: WLEDDevice) -> StoredBackup:
    return StoredBackup(
        backup_id=f"{device.device_id}/2026/09/27/030000",
        path=Path(f"C:/backups/{device.device_id}/2026/09/27/030000"),
        created_at=datetime(2026, 9, 27, 3, 0, 0, tzinfo=UTC),
        integration_version="1.0.0",
        device=StoredBackupDevice(
            name=device.name,
            host=device.host,
            mac=device.mac,
            device_id=device.device_id,
            firmware_version=device.firmware_version,
        ),
        files=(StoredBackupFile(name="cfg.json", size=2, sha256="hash"),),
    )


def _make_prune_result(device_id: str = "device-one") -> PruneResult:
    return PruneResult(
        dry_run=True,
        device_results=(
            DevicePruneResult(
                device_id=device_id,
                total_backups=3,
                kept_backup_ids=(f"{device_id}/keep",),
                would_delete_backup_ids=(f"{device_id}/drop",),
                deleted_backup_ids=(),
                failed_backup_ids=(),
            ),
        ),
    )


async def _register_services(hass: HomeAssistant) -> None:
    await integration.async_setup(hass, {})


@pytest.mark.asyncio
async def test_async_setup_registers_services_idempotently(
    hass: HomeAssistant,
) -> None:
    await _register_services(hass)
    await _register_services(hass)

    assert hass.services.has_service(DOMAIN, services_module.SERVICE_BACKUP)
    assert hass.services.has_service(DOMAIN, services_module.SERVICE_DISCOVER)


@pytest.mark.asyncio
async def test_services_registered_without_loaded_entry_raise_clear_error(
    hass: HomeAssistant,
) -> None:
    await _register_services(hass)

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            services_module.SERVICE_BACKUP_ALL,
            blocking=True,
            return_response=True,
        )
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "config_entry_not_loaded"


@pytest.mark.asyncio
async def test_services_with_unloaded_runtime_data_raise_clear_error(
    hass: HomeAssistant,
) -> None:
    await _register_services(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            services_module.SERVICE_DISCOVER,
            blocking=True,
            return_response=True,
        )
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "config_entry_not_ready"


@pytest.mark.asyncio
async def test_backup_action_returns_serialized_results(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register_services(hass)
    device = _make_device()
    manager = FakeManager(
        backup_result=_make_backup_result(),
        backup_all_results=[],
        backups=[],
        prune_result=_make_prune_result(),
        devices=[device],
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)

    async def resolve_devices(_hass: HomeAssistant, _call: object) -> list[WLEDDevice]:
        return [device]

    monkeypatch.setattr(
        services_module,
        "async_resolve_target_devices",
        resolve_devices,
    )

    response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_BACKUP,
        service_data={"include_presets": True, "device_id": [device.ha_device_id]},
        blocking=True,
        return_response=True,
    )

    assert response["results"][0]["device_id"] == "device-one"
    assert response["results"][0]["success"] is True


@pytest.mark.asyncio
async def test_backup_all_and_discover_return_response_data(
    hass: HomeAssistant,
) -> None:
    await _register_services(hass)
    device = _make_device()
    manager = FakeManager(
        backup_result=_make_backup_result(),
        backup_all_results=[_make_backup_result()],
        backups=[],
        prune_result=_make_prune_result(),
        devices=[device],
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)

    backup_all_response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_BACKUP_ALL,
        blocking=True,
        return_response=True,
    )
    discover_response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_DISCOVER,
        blocking=True,
        return_response=True,
    )

    assert (
        backup_all_response["results"][0]["backup_id"]
        == "device-one/2026/09/27/030000"
    )
    assert discover_response["devices"][0]["device_id"] == "device-one"


@pytest.mark.asyncio
async def test_list_backups_delete_backup_and_prune_actions(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register_services(hass)
    device = _make_device()
    backup = _make_stored_backup(device)
    manager = FakeManager(
        backup_result=_make_backup_result(),
        backup_all_results=[],
        backups=[backup],
        prune_result=_make_prune_result(),
        devices=[device],
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)

    async def resolve_devices(_hass: HomeAssistant, _call: object) -> list[WLEDDevice]:
        return [device]

    monkeypatch.setattr(
        services_module,
        "async_resolve_target_devices",
        resolve_devices,
    )

    list_response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_LIST_BACKUPS,
        service_data={"device_id": [device.ha_device_id], "limit": 1},
        blocking=True,
        return_response=True,
    )
    delete_response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_DELETE_BACKUP,
        service_data={"backup_id": backup.backup_id},
        blocking=True,
        return_response=True,
    )
    prune_response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_PRUNE,
        service_data={"device_id": [device.ha_device_id], "dry_run": True},
        blocking=True,
        return_response=True,
    )

    assert list_response["backups"][0]["backup_id"] == backup.backup_id
    assert delete_response == {"deleted": [backup.backup_id]}
    assert prune_response["dry_run"] is True
    assert manager.delete_calls == [backup.backup_id]


@pytest.mark.asyncio
async def test_restore_action_requires_one_device_and_is_not_ready(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register_services(hass)
    device = _make_device()
    manager = FakeManager(
        backup_result=_make_backup_result(),
        backup_all_results=[],
        backups=[],
        prune_result=_make_prune_result(),
        devices=[device],
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)

    async def resolve_none(_hass: HomeAssistant, _call: object) -> list[WLEDDevice]:
        return []

    monkeypatch.setattr(
        services_module,
        "async_resolve_target_devices",
        resolve_none,
    )
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            services_module.SERVICE_RESTORE,
            service_data={"backup_id": "device-one/2026/09/27/030000"},
            blocking=True,
            return_response=True,
        )
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "target_required"

    async def resolve_many(_hass: HomeAssistant, _call: object) -> list[WLEDDevice]:
        return [device, _make_device(device_id="device-two", host="10.0.0.11")]

    monkeypatch.setattr(
        services_module,
        "async_resolve_target_devices",
        resolve_many,
    )
    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            services_module.SERVICE_RESTORE,
            service_data={
                "backup_id": "device-one/2026/09/27/030000",
                "device_id": [device.ha_device_id],
            },
            blocking=True,
            return_response=True,
        )
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "restore_requires_single_device"

    async def resolve_one(_hass: HomeAssistant, _call: object) -> list[WLEDDevice]:
        return [device]


@pytest.mark.asyncio
async def test_resolve_target_device_errors_use_translation_keys(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = _make_device()

    monkeypatch.setattr(
        services_module,
        "async_resolve_target_devices",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            WLEDValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_device_target",
                translation_placeholders={"target": device.ha_device_id or "unknown"},
            )
        ),
    )

    with pytest.raises(WLEDValidationError) as exc_info:
        await services_module._resolve_devices_or_raise(
            hass,
            type("Call", (), {"data": {}, "target": {}})(),
            required=False,
        )

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "invalid_device_target"
async def test_restore_action_returns_response_when_manager_supports_it(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register_services(hass)
    device = _make_device()
    manager = FakeManager(
        backup_result=_make_backup_result(),
        backup_all_results=[],
        backups=[],
        prune_result=_make_prune_result(),
        devices=[device],
    )
    manager.restore_response = {"restored": True}
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)

    async def resolve_one(_hass: HomeAssistant, _call: object) -> list[WLEDDevice]:
        return [device]

    monkeypatch.setattr(services_module, "async_resolve_target_devices", resolve_one)

    response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_RESTORE,
        service_data={
            "backup_id": "device-one/2026/09/27/030000",
            "device_id": [device.ha_device_id],
        },
        blocking=True,
        return_response=True,
    )

    assert response == {"restored": True}


@pytest.mark.asyncio
async def test_list_backups_without_target_uses_manager_directly(
    hass: HomeAssistant,
) -> None:
    await _register_services(hass)
    device = _make_device()
    backup = _make_stored_backup(device)
    manager = FakeManager(
        backup_result=_make_backup_result(),
        backup_all_results=[],
        backups=[backup],
        prune_result=_make_prune_result(),
        devices=[device],
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)

    response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_LIST_BACKUPS,
        service_data={"limit": 1},
        blocking=True,
        return_response=True,
    )

    assert response["backups"][0]["backup_id"] == backup.backup_id


@pytest.mark.asyncio
async def test_prune_without_target_and_with_multiple_targets(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register_services(hass)
    device_one = _make_device(device_id="device-one")
    device_two = _make_device(device_id="device-two", host="10.0.0.11", name="Bedroom")
    manager = FakeManager(
        backup_result=_make_backup_result(),
        backup_all_results=[],
        backups=[],
        prune_result=_make_prune_result(device_id="device-one"),
        devices=[device_one, device_two],
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)

    response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_PRUNE,
        service_data={"dry_run": True},
        blocking=True,
        return_response=True,
    )
    assert response["device_results"][0]["device_id"] == "device-one"
    assert manager.prune_calls == [{"dry_run": True}]

    async def resolve_many(_hass: HomeAssistant, _call: object) -> list[WLEDDevice]:
        return [device_one, device_two]

    monkeypatch.setattr(services_module, "async_resolve_target_devices", resolve_many)
    response = await hass.services.async_call(
        DOMAIN,
        services_module.SERVICE_PRUNE,
        service_data={
            "device_id": [device_one.ha_device_id, device_two.ha_device_id],
            "dry_run": True,
        },
        blocking=True,
        return_response=True,
    )

    assert [item["device_id"] for item in response["device_results"]] == [
        "device-one",
        "device-two",
    ]


@pytest.mark.asyncio
async def test_non_wled_target_rejection_propagates(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _register_services(hass)
    manager = FakeManager(
        backup_result=_make_backup_result(),
        backup_all_results=[],
        backups=[],
        prune_result=_make_prune_result(),
        devices=[],
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)

    async def raise_non_wled(
        _hass: HomeAssistant,
        _call: object,
    ) -> list[WLEDDevice]:
        raise WLEDValidationError("not a Home Assistant WLED device")

    monkeypatch.setattr(
        services_module,
        "async_resolve_target_devices",
        raise_non_wled,
    )

    with pytest.raises(WLEDValidationError, match="not a Home Assistant WLED device"):
        await hass.services.async_call(
            DOMAIN,
            services_module.SERVICE_BACKUP,
            service_data={"device_id": ["bad-device"]},
            blocking=True,
            return_response=True,
        )