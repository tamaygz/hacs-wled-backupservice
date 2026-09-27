"""Tests for the restore engine implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from custom_components.wled_backupservice.discovery import WLEDDevice
from custom_components.wled_backupservice.exceptions import WLEDRestoreError
from custom_components.wled_backupservice.manager import WLEDBackupManager
from custom_components.wled_backupservice.models import BackupResult, RestoreResult
from custom_components.wled_backupservice.storage import (
    StoredBackup,
    StoredBackupDevice,
    StoredBackupFile,
)
from custom_components.wled_backupservice.wled_client import (
    WLEDClientCapabilities,
    WLEDInfo,
)


@dataclass
class FakeEntry:
    """Minimal config entry stand-in for restore tests."""

    options: dict[str, object]


class FakeStorage:
    """Storage stub exposing restore-oriented methods."""

    def __init__(self, descriptor: StoredBackup, files: dict[str, bytes]) -> None:
        self.descriptor = descriptor
        self.files = files
        self.read_file_calls: list[str] = []

    async def async_read_backup(self, backup_id: str) -> StoredBackup:
        assert backup_id == self.descriptor.backup_id
        return self.descriptor

    async def async_read_backup_file(self, backup_id: str, file_name: str) -> bytes:
        assert backup_id == self.descriptor.backup_id
        self.read_file_calls.append(file_name)
        return self.files[file_name]


class FakeRestoreClient:
    """Configurable restore client stub."""

    def __init__(
        self,
        *,
        info: WLEDInfo,
        config: dict[str, object] | None = None,
        presets: bytes | None = None,
        capabilities: WLEDClientCapabilities | None = None,
        set_config_error: Exception | None = None,
        upload_error: Exception | None = None,
        verify_config: dict[str, object] | None = None,
        verify_presets: bytes | None = None,
    ) -> None:
        self.info = info
        self.config = config or {"cfg": True}
        self.presets = presets or b'{"1": {}}'
        self.capabilities = capabilities or WLEDClientCapabilities(
            presets_upload_supported=True,
            presets_upload_verified=True,
        )
        self.set_config_error = set_config_error
        self.upload_error = upload_error
        self.verify_config = verify_config if verify_config is not None else self.config
        self.verify_presets = (
            verify_presets if verify_presets is not None else self.presets
        )
        self.calls: list[str] = []

    async def async_get_info(self) -> WLEDInfo:
        self.calls.append("get_info")
        return self.info

    async def async_set_config(self, config: dict[str, object]) -> None:
        self.calls.append("set_config")
        if self.set_config_error is not None:
            raise self.set_config_error

    async def async_upload_presets(self, payload: bytes) -> None:
        self.calls.append("upload_presets")
        if self.upload_error is not None:
            raise self.upload_error

    async def async_get_config(self) -> dict[str, object]:
        self.calls.append("verify_config")
        return self.verify_config

    async def async_get_presets_raw(self) -> bytes:
        self.calls.append("verify_presets")
        return self.verify_presets

    async def async_reboot(self) -> None:
        self.calls.append("reboot")


class LockAwareClient(FakeRestoreClient):
    """Client stub exposing set_config ordering for lock tests."""

    def __init__(self, *, info: WLEDInfo, events: list[str], host: str) -> None:
        super().__init__(info=info)
        self._events = events
        self._host = host

    async def async_set_config(self, config: dict[str, object]) -> None:
        self._events.append(f"start:{self._host}")
        await asyncio.sleep(0)
        self._events.append(f"end:{self._host}")
        await super().async_set_config(config)


def _make_manager(options: dict[str, object] | None = None) -> WLEDBackupManager:
    return WLEDBackupManager(hass=object(), entry=FakeEntry(options=options or {}))


def _make_device(
    *,
    device_id: str = "device-one",
    name: str = "Kitchen",
    host: str = "10.0.0.10",
    mac: str | None = "device-one",
) -> WLEDDevice:
    return WLEDDevice(
        device_id=device_id,
        name=name,
        host=host,
        mac=mac,
        ha_device_id=f"ha-{device_id}",
        ha_config_entry_id=f"entry-{device_id}",
        firmware_version="0.16.0",
    )


def _make_descriptor(device: WLEDDevice) -> StoredBackup:
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
            firmware_version="0.16.0",
        ),
        files=(
            StoredBackupFile(name="cfg.json", size=2, sha256="hash"),
            StoredBackupFile(name="presets.json", size=8, sha256="hash"),
        ),
    )


def _make_info(mac: str = "device-one", version: str = "0.16.0") -> WLEDInfo:
    return WLEDInfo(
        brand="WLED",
        product="FOSS",
        name="Kitchen",
        version=version,
        architecture="esp32",
        build_id=1,
        mac_address=mac,
        device_id=None,
    )


def _make_safety_backup(
    success: bool = True, backup_id: str | None = "safety/backup"
) -> BackupResult:
    """Create a synthetic safety-backup result for restore tests."""
    return BackupResult(
        device_id="device-one",
        device_name="Kitchen",
        success=success,
        backup_id=backup_id,
        path=Path("C:/backups/safety") if backup_id else None,
        files=("cfg.json",),
        created_at=None,
        error=None if success else "backup failed",
    )


@pytest.mark.asyncio
async def test_async_restore_applies_config_and_presets_sequentially() -> None:
    manager = _make_manager()
    device = _make_device()
    descriptor = _make_descriptor(device)
    storage = FakeStorage(
        descriptor, {"cfg.json": b'{"cfg": true}', "presets.json": b'{"1": {}}'}
    )
    client = FakeRestoreClient(
        info=_make_info(), config={"cfg": True}, presets=b'{"1": {}}'
    )
    manager.storage = storage
    manager.client_factory = lambda host: client

    async def fake_backup_device(*args: object, **kwargs: object) -> BackupResult:
        del args, kwargs
        return _make_safety_backup()

    manager.async_backup_device = fake_backup_device  # type: ignore[method-assign]

    result = await manager.async_restore(device, backup_id=descriptor.backup_id)

    assert isinstance(result, RestoreResult)
    assert result.success is True
    assert result.config_status == "ok"
    assert result.presets_status == "ok"
    assert result.verification_status == "ok"
    assert result.safety_backup_id == "safety/backup"
    assert client.calls == [
        "get_info",
        "set_config",
        "upload_presets",
        "verify_config",
        "verify_presets",
    ]


@pytest.mark.asyncio
async def test_async_restore_aborts_when_safety_backup_fails() -> None:
    manager = _make_manager()
    device = _make_device()
    descriptor = _make_descriptor(device)
    storage = FakeStorage(
        descriptor, {"cfg.json": b'{"cfg": true}', "presets.json": b'{"1": {}}'}
    )
    manager.storage = storage
    manager.client_factory = lambda host: FakeRestoreClient(info=_make_info())

    async def fake_backup_device(*args: object, **kwargs: object) -> BackupResult:
        del args, kwargs
        return _make_safety_backup(False, None)

    manager.async_backup_device = fake_backup_device  # type: ignore[method-assign]

    with pytest.raises(WLEDRestoreError, match="Safety backup failed"):
        await manager.async_restore(device, backup_id=descriptor.backup_id)


@pytest.mark.asyncio
async def test_async_restore_refuses_cross_device_restore() -> None:
    manager = _make_manager()
    device = _make_device(mac="device-one")
    descriptor = _make_descriptor(device)
    storage = FakeStorage(
        descriptor, {"cfg.json": b'{"cfg": true}', "presets.json": b'{"1": {}}'}
    )
    manager.storage = storage
    manager.client_factory = lambda host: FakeRestoreClient(
        info=_make_info(mac="other-device")
    )

    with pytest.raises(
        WLEDRestoreError,
        match="belongs to device-one, not other-device",
    ):
        await manager.async_restore(
            device,
            backup_id=descriptor.backup_id,
            backup_before_restore=False,
        )


@pytest.mark.asyncio
async def test_async_restore_warns_on_firmware_mismatch_and_skips_unverified_presets(
) -> None:
    manager = _make_manager()
    device = _make_device()
    descriptor = _make_descriptor(device)
    storage = FakeStorage(
        descriptor, {"cfg.json": b'{"cfg": true}', "presets.json": b'{"1": {}}'}
    )
    client = FakeRestoreClient(
        info=_make_info(version="0.17.0"),
        capabilities=WLEDClientCapabilities(
            presets_upload_supported=True,
            presets_upload_verified=False,
        ),
    )
    manager.storage = storage
    manager.client_factory = lambda host: client

    result = await manager.async_restore(
        device,
        backup_id=descriptor.backup_id,
        backup_before_restore=False,
    )

    assert result.success is True
    assert result.firmware_mismatch is True
    assert result.presets_status == "unsupported"
    assert "Preset restore is unavailable" in result.messages[1]


@pytest.mark.asyncio
async def test_async_restore_reports_partial_failure_on_verification_error() -> None:
    manager = _make_manager()
    device = _make_device()
    descriptor = _make_descriptor(device)
    storage = FakeStorage(
        descriptor, {"cfg.json": b'{"cfg": true}', "presets.json": b'{"1": {}}'}
    )
    client = FakeRestoreClient(
        info=_make_info(),
        verify_config={"cfg": False},
        capabilities=WLEDClientCapabilities(
            presets_upload_supported=False,
            presets_upload_verified=False,
        ),
    )
    manager.storage = storage
    manager.client_factory = lambda host: client

    result = await manager.async_restore(
        device,
        backup_id=descriptor.backup_id,
        backup_before_restore=False,
    )

    assert result.success is False
    assert result.config_status == "ok"
    assert result.verification_status == "failed"
    assert result.error == "Restore completed with warnings or partial failure"


@pytest.mark.asyncio
async def test_async_restore_reboots_after_config_restore() -> None:
    manager = _make_manager()
    device = _make_device()
    descriptor = _make_descriptor(device)
    storage = FakeStorage(
        descriptor, {"cfg.json": b'{"cfg": true}', "presets.json": b'{"1": {}}'}
    )
    client = FakeRestoreClient(
        info=_make_info(),
        capabilities=WLEDClientCapabilities(
            presets_upload_supported=False,
            presets_upload_verified=False,
        ),
    )
    manager.storage = storage
    manager.client_factory = lambda host: client

    result = await manager.async_restore(
        device,
        backup_id=descriptor.backup_id,
        backup_before_restore=False,
        reboot_after_restore=True,
    )

    assert result.rebooted is True
    assert "reboot" in client.calls


@pytest.mark.asyncio
async def test_async_restore_same_device_requests_are_serialized() -> None:
    manager = _make_manager()
    device = _make_device()
    descriptor = _make_descriptor(device)
    storage = FakeStorage(
        descriptor, {"cfg.json": b'{"cfg": true}', "presets.json": b'{"1": {}}'}
    )
    events: list[str] = []
    client = LockAwareClient(info=_make_info(), events=events, host=device.host)
    manager.storage = storage
    manager.client_factory = lambda host: client

    first, second = await asyncio.gather(
        manager.async_restore(
            device,
            backup_id=descriptor.backup_id,
            backup_before_restore=False,
            restore_presets=False,
        ),
        manager.async_restore(
            device,
            backup_id=descriptor.backup_id,
            backup_before_restore=False,
            restore_presets=False,
        ),
    )

    assert first.success and second.success
    assert events == [
        "start:10.0.0.10",
        "end:10.0.0.10",
        "start:10.0.0.10",
        "end:10.0.0.10",
    ]


@pytest.mark.asyncio
async def test_async_restore_supports_skipping_sections_and_verification() -> None:
    manager = _make_manager()
    device = _make_device()
    descriptor = _make_descriptor(device)
    storage = FakeStorage(
        descriptor,
        {"cfg.json": b'{"cfg": true}', "presets.json": b'{"1": {}}'},
    )
    client = FakeRestoreClient(info=_make_info())
    manager.storage = storage
    manager.client_factory = lambda host: client

    result = await manager.async_restore(
        device,
        backup_id=descriptor.backup_id,
        backup_before_restore=False,
        restore_config=False,
        restore_presets=False,
        verify_after_restore=False,
    )

    assert result.success is True
    assert result.config_status == "skipped"
    assert result.presets_status == "skipped"
    assert result.verification_status == "skipped"
    assert client.calls == ["get_info"]


@pytest.mark.asyncio
async def test_async_restore_reports_presets_verification_failure() -> None:
    manager = _make_manager()
    device = _make_device()
    descriptor = _make_descriptor(device)
    storage = FakeStorage(
        descriptor,
        {"cfg.json": b'{"cfg": true}', "presets.json": b'{"1": {}}'},
    )
    client = FakeRestoreClient(
        info=_make_info(),
        verify_presets=b'{"1": {"changed": true}}',
    )
    manager.storage = storage
    manager.client_factory = lambda host: client

    result = await manager.async_restore(
        device,
        backup_id=descriptor.backup_id,
        backup_before_restore=False,
        restore_config=False,
    )

    assert result.success is False
    assert result.presets_status == "ok"
    assert result.verification_status == "failed"
    assert "Presets verification failed after restore" in result.messages


@pytest.mark.asyncio
async def test_async_restore_rejects_unexpected_kwargs() -> None:
    manager = _make_manager()
    device = _make_device()

    with pytest.raises(TypeError, match="Unexpected restore kwargs"):
        await manager.async_restore(
            device,
            backup_id="device-one/2026/09/27/030000",
            unexpected=True,
        )
