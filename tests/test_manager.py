"""Tests for the WLED backup engine in the manager."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

import custom_components.wled_backupservice.manager as manager_module
from custom_components.wled_backupservice.discovery import WLEDDevice
from custom_components.wled_backupservice.exceptions import (
    WLEDConnectionError,
    WLEDValidationError,
)
from custom_components.wled_backupservice.manager import WLEDBackupManager
from custom_components.wled_backupservice.storage import (
    StoredBackup,
    StoredBackupDevice,
    StoredBackupFile,
)
from custom_components.wled_backupservice.wled_client import WLEDInfo


@dataclass
class FakeEntry:
    """Minimal config entry stand-in for manager tests."""

    options: dict[str, object]
    entry_id: str = "test-entry"
    unload_callbacks: list[Any] = field(default_factory=list)

    def async_on_unload(self, callback: Any) -> None:
        self.unload_callbacks.append(callback)

    def async_create_background_task(
        self,
        hass: Any,
        target: Any,
        name: str,
        eager_start: bool = False,
    ) -> asyncio.Task[Any]:
        del eager_start
        return hass.async_create_background_task(target, name)


class RecordingStorage:
    """Fake storage that records backup write arguments."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.backups: list[StoredBackup] = []
        self.deleted_ids: list[str] = []

    async def async_write_backup(self, **kwargs: object) -> StoredBackup:
        self.calls.append(kwargs)
        files = cast(dict[str, bytes], kwargs["files"])
        created_at = datetime(2026, 9, 27, 3, 0, 0, tzinfo=UTC)
        mac = kwargs.get("mac")
        firmware_version = kwargs.get("firmware_version")
        normalized_mac = mac if isinstance(mac, str | type(None)) else None
        normalized_firmware_version = (
            firmware_version
            if isinstance(firmware_version, str | type(None))
            else None
        )
        return StoredBackup(
            backup_id="kitchen/2026/09/27/030000",
            path=Path("C:/backups/kitchen/2026/09/27/030000"),
            created_at=created_at,
            integration_version="unknown",
            device=StoredBackupDevice(
                name=str(kwargs["device_name"]),
                host=str(kwargs["host"]),
                mac=normalized_mac,
                device_id=str(kwargs["device_id"]),
                firmware_version=normalized_firmware_version,
            ),
            files=tuple(
                StoredBackupFile(name=name, size=len(content), sha256="hash")
                for name, content in files.items()
            ),
        )

    async def async_list(self, device_id: str | None = None) -> list[StoredBackup]:
        if device_id is None:
            return list(self.backups)
        return [
            backup
            for backup in self.backups
            if backup.device.device_id == device_id
        ]

    async def async_delete(self, backup_id: str) -> None:
        self.deleted_ids.append(backup_id)


class FakeRetention:
    """Retention stub used by manager prune tests."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def async_prune_backups(self, storage: object, **kwargs: object) -> object:
        self.calls.append({"storage": storage, **kwargs})
        return self.result


class FakeClient:
    """Configurable fake WLED client."""

    def __init__(
        self,
        *,
        info: WLEDInfo,
        config: dict[str, object] | None = None,
        presets: bytes | None = None,
        state: dict[str, object] | None = None,
        config_error: Exception | None = None,
        state_error: Exception | None = None,
    ) -> None:
        self.info = info
        self.config = config or {"wifi": {}}
        self.presets = presets if presets is not None else b'{"1": {}}'
        self.state = state or {"on": True}
        self.config_error = config_error
        self.state_error = state_error

    async def async_get_info(self) -> WLEDInfo:
        return self.info

    async def async_get_config(self) -> dict[str, object]:
        if self.config_error is not None:
            raise self.config_error
        return self.config

    async def async_get_presets_raw(self) -> bytes:
        return self.presets

    async def async_get_state(self) -> dict[str, object]:
        if self.state_error is not None:
            raise self.state_error
        return self.state


class LockStepClient(FakeClient):
    """Client that exposes entry/exit order for lock serialization tests."""

    def __init__(self, *, info: WLEDInfo, events: list[str], host: str) -> None:
        super().__init__(info=info)
        self._events = events
        self._host = host

    async def async_get_config(self) -> dict[str, object]:
        self._events.append(f"start:{self._host}")
        await asyncio.sleep(0)
        self._events.append(f"end:{self._host}")
        return await super().async_get_config()


def _make_manager(options: dict[str, object] | None = None) -> WLEDBackupManager:
    """Create a manager with a minimal fake config entry."""
    return WLEDBackupManager(hass=object(), entry=FakeEntry(options=options or {}))


def _make_runtime_manager(
    options: dict[str, object] | None = None,
) -> WLEDBackupManager:
    """Create a manager with a fake hass object that supports lazy wiring."""
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
    return WLEDBackupManager(hass=hass, entry=FakeEntry(options=options or {}))


def _make_device(
    *,
    device_id: str = "aabbccddeeff",
    name: str = "Kitchen",
    host: str = "10.0.0.10",
    mac: str | None = "aabbccddeeff",
) -> WLEDDevice:
    """Create a fake discovered WLED device."""
    return WLEDDevice(
        device_id=device_id,
        name=name,
        host=host,
        mac=mac,
        ha_device_id="ha-device",
        ha_config_entry_id="ha-entry",
        firmware_version=None,
    )


@pytest.mark.asyncio
async def test_async_backup_device_writes_selected_artifacts() -> None:
    """Single-device backup should verify, fetch selected artifacts, and store them."""
    manager = _make_manager({"include_presets": True, "include_state": False})
    storage = RecordingStorage()
    info = WLEDInfo(
        brand="WLED",
        product="FOSS",
        name="Kitchen",
        version="0.16.0",
        architecture="esp32",
        build_id=2601010,
        mac_address="aabbccddeeff",
        device_id="wled-aabbccddeeff",
    )
    manager.storage = storage
    manager.client_factory = lambda host: FakeClient(info=info)

    result = await manager.async_backup_device(_make_device())

    assert result.success is True
    assert manager.last_backup_status == "success"
    assert manager.last_backup_success is not None
    assert manager.last_error is None
    assert result.backup_id == "kitchen/2026/09/27/030000"
    assert set(result.files) == {"cfg.json", "info.json", "presets.json"}
    assert len(storage.calls) == 1
    stored_files = cast(dict[str, bytes], storage.calls[0]["files"])
    assert set(stored_files) == {"cfg.json", "info.json", "presets.json"}
    assert storage.calls[0]["device_id"] == "wled-aabbccddeeff"
    assert storage.calls[0]["mac"] == "aabbccddeeff"


@pytest.mark.asyncio
async def test_async_backup_device_uses_explicit_state_override() -> None:
    """Explicit include_state should override entry defaults."""
    manager = _make_manager({"include_presets": False, "include_state": False})
    storage = RecordingStorage()
    info = WLEDInfo(
        brand="WLED",
        product=None,
        name="Kitchen",
        version="0.16.0",
        architecture="esp32",
        build_id=2601010,
        mac_address="aabbccddeeff",
        device_id=None,
    )
    manager.storage = storage
    manager.client_factory = lambda host: FakeClient(info=info)

    result = await manager.async_backup_device(
        _make_device(),
        include_presets=False,
        include_state=True,
    )

    assert result.success is True
    stored_files = cast(dict[str, bytes], storage.calls[0]["files"])
    assert set(stored_files) == {"cfg.json", "info.json", "state.json"}


@pytest.mark.asyncio
async def test_async_backup_all_is_fail_soft() -> None:
    """Bulk backup should continue when one device fails."""
    manager = _make_manager()
    storage = RecordingStorage()
    healthy = _make_device(device_id="one", name="One", host="10.0.0.1", mac="one")
    failing = _make_device(device_id="two", name="Two", host="10.0.0.2", mac="two")
    manager.storage = storage
    manager.discovery = type(
        "Discovery",
        (),
        {
            "async_discover_wled_devices": staticmethod(
                lambda hass: asyncio.sleep(0, result=[healthy, failing])
            )
        },
    )()

    good_info = WLEDInfo(
        brand="WLED",
        product=None,
        name="One",
        version="0.16.0",
        architecture="esp32",
        build_id=1,
        mac_address="one",
        device_id=None,
    )
    manager.client_factory = lambda host: (
        FakeClient(info=good_info)
        if host == "10.0.0.1"
        else FakeClient(info=good_info, config_error=WLEDConnectionError("offline"))
    )

    results = await manager.async_backup_all()

    assert [result.success for result in results] == [True, False]
    assert results[1].error == "offline"
    assert manager.discovered_device_count == 2
    assert manager.last_backup_status == "partial_failure"
    assert manager.last_error == "offline"
    assert len(storage.calls) == 1


@pytest.mark.asyncio
async def test_async_backup_device_warns_on_mac_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A mismatch between discovered and verified MAC should warn and continue."""
    manager = _make_manager()
    storage = RecordingStorage()
    info = WLEDInfo(
        brand="WLED",
        product=None,
        name="Kitchen",
        version="0.16.0",
        architecture="esp32",
        build_id=1,
        mac_address="ffeeddccbbaa",
        device_id=None,
    )
    manager.storage = storage
    manager.client_factory = lambda host: FakeClient(info=info)

    result = await manager.async_backup_device(_make_device(mac="aabbccddeeff"))

    assert result.success is True
    assert "differs from verified MAC" in caplog.text
    assert storage.calls[0]["mac"] == "aabbccddeeff"


@pytest.mark.asyncio
async def test_async_backup_device_rejects_non_wled_brand() -> None:
    """A verified device with the wrong brand should fail validation."""
    manager = _make_manager()
    info = WLEDInfo(
        brand="Other",
        product=None,
        name="Kitchen",
        version="0.16.0",
        architecture="esp32",
        build_id=1,
        mac_address="aabbccddeeff",
        device_id=None,
    )
    manager.storage = RecordingStorage()
    manager.client_factory = lambda host: FakeClient(info=info)

    result = await manager.async_backup_device(_make_device())

    assert result.success is False
    assert manager.last_backup_status == "failed"
    assert manager.last_error == "Expected WLED device at 10.0.0.10, got 'Other'"
    assert result.error == "Expected WLED device at 10.0.0.10, got 'Other'"


@pytest.mark.asyncio
async def test_async_backup_device_serializes_same_device_calls() -> None:
    """Concurrent backup requests for the same device should be serialized by lock."""
    manager = _make_manager()
    storage = RecordingStorage()
    events: list[str] = []
    info = WLEDInfo(
        brand="WLED",
        product=None,
        name="Kitchen",
        version="0.16.0",
        architecture="esp32",
        build_id=1,
        mac_address="aabbccddeeff",
        device_id=None,
    )
    manager.storage = storage
    manager.client_factory = lambda host: LockStepClient(
        info=info,
        events=events,
        host=host,
    )
    device = _make_device()

    first, second = await asyncio.gather(
        manager.async_backup_device(device),
        manager.async_backup_device(device),
    )

    assert first.success and second.success
    assert events == [
        "start:10.0.0.10",
        "end:10.0.0.10",
        "start:10.0.0.10",
        "end:10.0.0.10",
    ]


@pytest.mark.asyncio
async def test_async_discover_devices_delegates_to_discovery_module() -> None:
    """Manager discovery should delegate to the configured discovery collaborator."""
    manager = _make_manager()
    devices = [_make_device()]
    manager.discovery = type(
        "Discovery",
        (),
        {
            "async_discover_wled_devices": staticmethod(
                lambda hass: asyncio.sleep(0, result=devices)
            )
        },
    )()

    discovered = await manager.async_discover_devices()

    assert discovered == devices


@pytest.mark.asyncio
async def test_async_setup_and_shutdown_toggle_runtime_state() -> None:
    """Lifecycle hooks should update manager runtime state."""
    manager = _make_manager({"schedule_enabled": False})

    await manager.async_setup()
    assert manager.is_setup is True
    assert manager.is_shutdown is False

    manager.scheduler_unsub = lambda: None
    await manager.async_shutdown()
    assert manager.is_shutdown is True
    assert manager.scheduler_unsub is None


@pytest.mark.asyncio
async def test_async_setup_registers_interval_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _make_runtime_manager(
        {
            "schedule_enabled": True,
            "interval": 2,
            "interval_unit": "hours",
            "daily_time": "06:30:00",
        }
    )
    captured: dict[str, Any] = {}
    unsub_called = False

    def _unsub() -> None:
        nonlocal unsub_called
        unsub_called = True

    def _track_interval(hass: Any, action: Any, interval: Any) -> Any:
        captured["hass"] = hass
        captured["action"] = action
        captured["interval"] = interval
        return _unsub

    monkeypatch.setattr(
        manager_module.event,
        "async_track_time_interval",
        _track_interval,
    )
    monkeypatch.setattr(
        manager_module.event,
        "async_track_time_change",
        lambda *args: pytest.fail("daily schedule should not be used"),
    )

    await manager.async_setup()

    assert captured["hass"] is manager.hass
    assert captured["action"] == manager._async_handle_scheduled_tick
    assert captured["interval"].total_seconds() == 7200
    assert manager.scheduler_unsub is _unsub

    manager.entry.unload_callbacks[0]()

    assert unsub_called is True
    assert manager.scheduler_unsub is None


@pytest.mark.asyncio
async def test_async_setup_registers_daily_scheduler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _make_runtime_manager(
        {
            "schedule_enabled": True,
            "interval": 1,
            "interval_unit": "days",
            "daily_time": "06:30:15",
        }
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        manager_module.event,
        "async_track_time_interval",
        lambda *args: pytest.fail("interval schedule should not be used"),
    )

    def _track_daily(
        hass: Any,
        action: Any,
        *,
        hour: int,
        minute: int,
        second: int,
    ) -> Any:
        captured["hass"] = hass
        captured["action"] = action
        captured["time"] = (hour, minute, second)
        return lambda: None

    monkeypatch.setattr(manager_module.event, "async_track_time_change", _track_daily)

    await manager.async_setup()

    assert captured["hass"] is manager.hass
    assert captured["action"] == manager._async_handle_scheduled_tick
    assert captured["time"] == (6, 30, 15)


@pytest.mark.asyncio
async def test_async_setup_skips_scheduler_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _make_runtime_manager({"schedule_enabled": False})
    interval_mock = AsyncMock()
    daily_mock = AsyncMock()
    monkeypatch.setattr(
        manager_module.event,
        "async_track_time_interval",
        interval_mock,
    )
    monkeypatch.setattr(manager_module.event, "async_track_time_change", daily_mock)

    await manager.async_setup()

    interval_mock.assert_not_called()
    daily_mock.assert_not_called()
    assert manager.scheduler_unsub is None


@pytest.mark.asyncio
async def test_async_run_scheduled_cycle_prunes_after_backups() -> None:
    manager = _make_runtime_manager()
    events: list[str] = []
    backup_result = [
        manager_module.BackupResult(
            device_id="device-one",
            device_name="Kitchen",
            success=True,
            backup_id="device-one/2026/09/27/030000",
            path=Path("C:/backups/device-one/2026/09/27/030000"),
            files=("cfg.json",),
            created_at=datetime(2026, 9, 27, 3, 0, 0, tzinfo=UTC),
            error=None,
        )
    ]

    async def _backup_all(**kwargs: Any) -> list[Any]:
        events.append(f"backup:{kwargs['include_presets']}:{kwargs['include_state']}")
        return backup_result

    async def _prune() -> object:
        events.append("prune")
        return object()

    manager.async_backup_all = _backup_all  # type: ignore[method-assign]
    manager.async_prune = _prune  # type: ignore[method-assign]

    await manager.async_run_scheduled_cycle()

    assert events == ["backup:True:False", "prune"]


@pytest.mark.asyncio
async def test_scheduled_tick_skips_when_cycle_is_already_running() -> None:
    manager = _make_runtime_manager()
    running_task = asyncio.create_task(asyncio.sleep(60))
    manager.scheduled_cycle_task = running_task

    try:
        manager._async_handle_scheduled_tick(datetime.now(UTC))
        assert manager.scheduled_cycle_task is running_task
    finally:
        running_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running_task


@pytest.mark.asyncio
async def test_scheduled_tick_creates_background_task_once_previous_cycle_finishes(
) -> None:
    manager = _make_runtime_manager({"schedule_enabled": False})
    gate = asyncio.Event()
    started = asyncio.Event()

    async def _run_cycle() -> None:
        started.set()
        await gate.wait()

    manager.async_run_scheduled_cycle = _run_cycle  # type: ignore[method-assign]

    manager._async_handle_scheduled_tick(datetime.now(UTC))
    await started.wait()
    first_task = manager.scheduled_cycle_task
    assert first_task is not None

    manager._async_handle_scheduled_tick(datetime.now(UTC))
    assert manager.scheduled_cycle_task is first_task

    gate.set()
    await first_task
    await asyncio.sleep(0)

    manager._async_handle_scheduled_tick(datetime.now(UTC))
    second_task = manager.scheduled_cycle_task
    assert second_task is not None
    assert second_task is not first_task
    await second_task
def test_bool_option_json_bytes_and_lock_helpers() -> None:
    """Small manager helpers should resolve options deterministically."""
    manager = _make_manager({"include_presets": False})

    assert manager._bool_option("include_presets", True, None) is False
    assert manager._bool_option("include_presets", True, True) is True
    assert manager._json_bytes({"b": 1, "a": 2}) == b'{\n  "a": 2,\n  "b": 1\n}'

    first = manager._async_get_device_lock("device")
    second = manager._async_get_device_lock("device")
    assert first is second


def test_validate_verified_info_requires_identity() -> None:
    """Verified info without a usable identity should fail validation."""
    manager = _make_manager()
    info = WLEDInfo(
        brand="WLED",
        product=None,
        name="Kitchen",
        version="0.16.0",
        architecture="esp32",
        build_id=1,
        mac_address="",
        device_id=None,
    )

    with pytest.raises(WLEDValidationError, match="did not report a usable identity"):
        manager._validate_verified_info(_make_device(mac=None), info)


def test_ensure_client_factory_wires_shared_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lazy client wiring should bind the HA shared session into the client factory."""
    manager = _make_runtime_manager()
    session = object()
    captured: dict[str, object] = {}

    class FakeRuntimeClient:
        def __init__(self, host: str, provided_session: object) -> None:
            captured["host"] = host
            captured["session"] = provided_session

    monkeypatch.setattr(manager_module, "async_get_clientsession", lambda hass: session)
    monkeypatch.setattr(
        "custom_components.wled_backupservice.wled_client.WLEDClient",
        FakeRuntimeClient,
    )

    manager._ensure_client_factory()
    client_factory = manager.client_factory
    assert client_factory is not None
    client_factory("10.0.0.10")

    assert captured == {"host": "10.0.0.10", "session": session}


def test_ensure_storage_uses_entry_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lazy storage wiring should honor config-entry storage options."""
    manager = _make_runtime_manager(
        {"storage_root": "backup", "subdir": "custom_backups"}
    )
    captured: dict[str, object] = {}

    class FakeRuntimeStorage:
        def __init__(
            self,
            hass: object,
            *,
            storage_root: str,
            subdir: str,
            integration_version: str = "unknown",
        ) -> None:
            captured["hass"] = hass
            captured["storage_root"] = storage_root
            captured["subdir"] = subdir
            captured["integration_version"] = integration_version

    monkeypatch.setattr(
        "custom_components.wled_backupservice.storage.BackupStorage",
        FakeRuntimeStorage,
    )

    manager._ensure_storage()

    assert captured["hass"] is manager.hass
    assert captured["storage_root"] == "backup"
    assert captured["subdir"] == "custom_backups"
    assert captured["integration_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_async_list_and_delete_backups_delegate_to_storage() -> None:
    manager = _make_manager()
    storage = RecordingStorage()
    storage.backups = [
        StoredBackup(
            backup_id="device-one/2026/09/27/030000",
            path=Path("C:/backups/device-one/2026/09/27/030000"),
            created_at=datetime(2026, 9, 27, 3, 0, 0, tzinfo=UTC),
            integration_version="1.0.0",
            device=StoredBackupDevice(
                name="Kitchen",
                host="10.0.0.10",
                mac="device-one",
                device_id="device-one",
                firmware_version="0.16.0",
            ),
            files=(StoredBackupFile(name="cfg.json", size=2, sha256="hash"),),
        )
    ]
    manager.storage = storage

    backups = await manager.async_list_backups(
        device=_make_device(device_id="device-one")
    )
    await manager.async_delete_backup(backup_id="device-one/2026/09/27/030000")

    assert len(backups) == 1
    assert backups[0].backup_id == "device-one/2026/09/27/030000"
    assert storage.deleted_ids == ["device-one/2026/09/27/030000"]


@pytest.mark.asyncio
async def test_async_prune_delegates_with_option_defaults() -> None:
    manager = _make_manager({"retention_count": 5, "retention_days": 2})
    storage = RecordingStorage()
    retention_result = object()
    retention = FakeRetention(retention_result)
    manager.storage = storage
    manager.retention = retention

    result = await manager.async_prune(
        device=_make_device(device_id="device-one"),
        dry_run=True,
    )

    assert result is retention_result
    assert retention.calls == [
        {
            "storage": storage,
            "retention_count": 5,
            "retention_days": 2,
            "device": _make_device(device_id="device-one"),
            "dry_run": True,
        }
    ]