"""Tests for the WLED discovery adapter."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.wled_backupservice.discovery import (
    WLEDDevice,
    _sanitize_host,
    async_discover_wled_devices,
    async_resolve_target_devices,
)
from custom_components.wled_backupservice.exceptions import WLEDValidationError


class FakeConfigEntries:
    """Minimal config entry manager for discovery tests."""

    def __init__(self, entries: list[SimpleNamespace]) -> None:
        self._entries = entries
        self._entries_by_id = {entry.entry_id: entry for entry in entries}

    def async_entries(self, domain: str) -> list[SimpleNamespace]:
        """Return config entries for a domain."""
        return [entry for entry in self._entries if entry.domain == domain]

    def async_get_entry(self, entry_id: str) -> SimpleNamespace | None:
        """Return a config entry by id."""
        return self._entries_by_id.get(entry_id)


class FakeDeviceRegistry:
    """Minimal device registry for discovery tests."""

    def __init__(self, devices: list[SimpleNamespace]) -> None:
        self._devices_by_id = {device.id: device for device in devices}

    def async_get(self, device_id: str) -> SimpleNamespace | None:
        """Return a registry device by Home Assistant device id."""
        return self._devices_by_id.get(device_id)

    def async_get_device(
        self,
        identifiers: set[tuple[str, str]] | None = None,
        connections: set[tuple[str, str]] | None = None,
    ) -> SimpleNamespace | None:
        """Return a matching registry device by identifier or connection."""
        identifiers = identifiers or set()
        connections = connections or set()
        for device in self._devices_by_id.values():
            if identifiers and identifiers & getattr(device, "identifiers", set()):
                return device
            if connections and connections & getattr(device, "connections", set()):
                return device
        return None


def _make_entry(
    entry_id: str,
    host: str | None,
    unique_id: str | None,
    title: str,
    domain: str = "wled",
) -> SimpleNamespace:
    """Build a fake config entry."""
    data = {}
    if host is not None:
        data["host"] = host
    return SimpleNamespace(
        entry_id=entry_id,
        data=data,
        unique_id=unique_id,
        title=title,
        domain=domain,
    )


def _make_registry_device(
    device_id: str,
    *,
    entry_id: str,
    mac: str,
    name: str,
    sw_version: str | None = None,
    identifiers: set[tuple[str, str]] | None = None,
    connections: set[tuple[str, str]] | None = None,
) -> SimpleNamespace:
    """Build a fake device registry entry."""
    return SimpleNamespace(
        id=device_id,
        name=name,
        sw_version=sw_version,
        config_entries={entry_id},
        identifiers=identifiers or {("wled", mac)},
        connections=connections
        or {
            (
                "mac",
                f"{mac[0:2]}:{mac[2:4]}:{mac[4:6]}:{mac[6:8]}:{mac[8:10]}:{mac[10:12]}",
            )
        },
    )


def test_async_discover_wled_devices_returns_empty_list(socket_enabled: None) -> None:
    """No WLED entries should produce an empty discovery result."""
    _ = socket_enabled
    hass = SimpleNamespace(config_entries=FakeConfigEntries([]))
    registry = FakeDeviceRegistry([])

    from custom_components.wled_backupservice import discovery

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(discovery.dr, "async_get", lambda _hass: registry)
        devices = asyncio.run(async_discover_wled_devices(hass))

    assert devices == []


def test_async_discover_wled_devices_maps_entries_and_registry_data(
    socket_enabled: None,
) -> None:
    """Discovery should map WLED config entries to stable WLEDDevice objects."""
    _ = socket_enabled
    entry_one = _make_entry("entry-one", "10.0.0.10", "aabbccddeeff", "Kitchen")
    entry_two = _make_entry("entry-two", "10.0.0.10", "112233445566", "Kitchen")
    hass = SimpleNamespace(config_entries=FakeConfigEntries([entry_one, entry_two]))
    registry = FakeDeviceRegistry(
        [
            _make_registry_device(
                "ha-device-one",
                entry_id="entry-one",
                mac="aabbccddeeff",
                name="Kitchen",
                sw_version="0.14.1",
            ),
            _make_registry_device(
                "ha-device-two",
                entry_id="entry-two",
                mac="112233445566",
                name="Kitchen",
                sw_version="0.14.2",
            ),
        ]
    )

    from custom_components.wled_backupservice import discovery

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(discovery.dr, "async_get", lambda _hass: registry)
        devices = asyncio.run(async_discover_wled_devices(hass))

    assert devices == [
        WLEDDevice(
            device_id="aabbccddeeff",
            name="Kitchen",
            host="10.0.0.10",
            mac="aabbccddeeff",
            ha_device_id="ha-device-one",
            ha_config_entry_id="entry-one",
            firmware_version="0.14.1",
        ),
        WLEDDevice(
            device_id="112233445566",
            name="Kitchen",
            host="10.0.0.10",
            mac="112233445566",
            ha_device_id="ha-device-two",
            ha_config_entry_id="entry-two",
            firmware_version="0.14.2",
        ),
    ]


def test_async_discover_wled_devices_skips_missing_host_and_falls_back_without_registry(
    socket_enabled: None,
) -> None:
    """Entries without hosts are skipped, while host-only entries still discover."""
    _ = socket_enabled
    skipped_entry = _make_entry("entry-skip", None, "aabbccddeeff", "Skip")
    host_only_entry = _make_entry("entry-host", "wled.local", None, "Offline")
    hass = SimpleNamespace(
        config_entries=FakeConfigEntries([skipped_entry, host_only_entry])
    )
    registry = FakeDeviceRegistry([])

    from custom_components.wled_backupservice import discovery

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(discovery.dr, "async_get", lambda _hass: registry)
        devices = asyncio.run(async_discover_wled_devices(hass))

    assert devices == [
        WLEDDevice(
            device_id="wled_local",
            name="Offline",
            host="wled.local",
            mac=None,
            ha_device_id=None,
            ha_config_entry_id="entry-host",
            firmware_version=None,
        )
    ]


def test_async_resolve_target_devices_rejects_non_wled_targets(
    socket_enabled: None,
) -> None:
    """Target resolution should reject non-WLED Home Assistant device ids."""
    _ = socket_enabled
    wled_entry = _make_entry("entry-wled", "10.0.0.10", "aabbccddeeff", "Kitchen")
    other_entry = _make_entry(
        "entry-other",
        "10.0.0.20",
        "998877665544",
        "Other",
        domain="light",
    )
    hass = SimpleNamespace(
        config_entries=FakeConfigEntries([wled_entry, other_entry])
    )
    registry = FakeDeviceRegistry(
        [
            _make_registry_device(
                "ha-device-wled",
                entry_id="entry-wled",
                mac="aabbccddeeff",
                name="Kitchen",
            ),
            _make_registry_device(
                "ha-device-other",
                entry_id="entry-other",
                mac="998877665544",
                name="Other",
                identifiers={("light", "998877665544")},
            ),
        ]
    )
    call = SimpleNamespace(data={"device_id": "ha-device-other"})

    from custom_components.wled_backupservice import discovery

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(discovery.dr, "async_get", lambda _hass: registry)
        with pytest.raises(
            WLEDValidationError,
            match="not a Home Assistant WLED device",
        ):
            asyncio.run(async_resolve_target_devices(hass, call))


def test_async_resolve_target_devices_returns_targeted_wled_devices(
    socket_enabled: None,
) -> None:
    """Target resolution should map HA device ids back to discovered WLED devices."""
    _ = socket_enabled
    entry = _make_entry("entry-one", "10.0.0.10", "aabbccddeeff", "Kitchen")
    hass = SimpleNamespace(config_entries=FakeConfigEntries([entry]))
    registry = FakeDeviceRegistry(
        [
            _make_registry_device(
                "ha-device-one",
                entry_id="entry-one",
                mac="aabbccddeeff",
                name="Kitchen",
                sw_version="0.14.1",
            )
        ]
    )
    call = SimpleNamespace(data={"device_id": ["ha-device-one"]})

    from custom_components.wled_backupservice import discovery

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(discovery.dr, "async_get", lambda _hass: registry)
        devices = asyncio.run(async_resolve_target_devices(hass, call))

    assert devices == [
        WLEDDevice(
            device_id="aabbccddeeff",
            name="Kitchen",
            host="10.0.0.10",
            mac="aabbccddeeff",
            ha_device_id="ha-device-one",
            ha_config_entry_id="entry-one",
            firmware_version="0.14.1",
        )
    ]


def test_sanitize_host_creates_stable_fallback_identity() -> None:
    """Host fallback identities should be lowercase and separator-safe."""
    assert _sanitize_host("WLED-Local_01") == "wled_local_01"