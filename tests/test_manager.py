"""Tests for the WLED backup engine in the manager."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

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


class RecordingStorage:
    """Fake storage that records backup write arguments."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
    hass = SimpleNamespace(
        data={},
        config=SimpleNamespace(path=lambda *_parts: "config"),
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
    manager = _make_manager()

    await manager.async_setup()
    assert manager.is_setup is True
    assert manager.is_shutdown is False

    manager.scheduler_unsub = object()
    await manager.async_shutdown()
    assert manager.is_shutdown is True
    assert manager.scheduler_unsub is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    [
        "async_restore",
    ],
)
async def test_unimplemented_manager_methods_raise(method_name: str) -> None:
    """Out-of-scope manager methods should remain explicit stubs in this slice."""
    manager = _make_manager()

    with pytest.raises(NotImplementedError):
        await getattr(manager, method_name)()


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