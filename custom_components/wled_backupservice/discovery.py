"""WLED discovery adapter.

This module isolates Home Assistant version-sensitive assumptions about how the
native `wled` integration stores host and identity information, and how the
device registry can be queried for config-entry-owned devices.

Verified against the local Home Assistant development stack on 2026-09-27:
- WLED config entries store the host in `entry.data[CONF_HOST]`
- WLED config entries use the device MAC address as `entry.unique_id`
- Home Assistant 2024.3 exposes `DeviceRegistry.async_get_device(...)` rather
  than the newer scoped `async_get_device_by_identifier(...)` helpers
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from .const import LOGGER, WLED_DOMAIN
from .exceptions import WLEDValidationError


@dataclass(frozen=True)
class WLEDDevice:
    """Stable representation of a discoverable WLED device."""

    device_id: str
    name: str
    host: str
    mac: str | None
    ha_device_id: str | None
    ha_config_entry_id: str | None
    firmware_version: str | None


async def async_discover_wled_devices(hass: HomeAssistant) -> list[WLEDDevice]:
    """Discover WLED devices already configured in Home Assistant."""
    registry = dr.async_get(hass)
    devices: list[WLEDDevice] = []

    for entry in hass.config_entries.async_entries(WLED_DOMAIN):
        host = entry.data.get(CONF_HOST)
        if not host:
            LOGGER.warning(
                "Skipping WLED config entry %s because it has no host",
                entry.entry_id,
            )
            continue

        mac = _normalize_mac(entry.unique_id)
        registry_device = _find_registry_device(registry, entry, mac)
        devices.append(
            WLEDDevice(
                device_id=mac or _sanitize_host(host),
                name=entry.title or (registry_device.name if registry_device else host),
                host=host,
                mac=mac,
                ha_device_id=registry_device.id if registry_device else None,
                ha_config_entry_id=entry.entry_id,
                firmware_version=(
                    registry_device.sw_version if registry_device else None
                ),
            )
        )

    return devices


async def async_resolve_target_devices(
    hass: HomeAssistant,
    call: ServiceCall | Any,
) -> list[WLEDDevice]:
    """Resolve targeted HA device ids to discovered WLED devices."""
    discovered = await async_discover_wled_devices(hass)
    target_device_ids = _extract_target_device_ids(call)
    if not target_device_ids:
        return discovered

    registry = dr.async_get(hass)
    devices_by_ha_id = {
        device.ha_device_id: device
        for device in discovered
        if device.ha_device_id is not None
    }

    resolved: list[WLEDDevice] = []
    for target_device_id in target_device_ids:
        registry_device = registry.async_get(target_device_id)
        if registry_device is None or not _is_wled_registry_device(
            hass, registry_device
        ):
            raise WLEDValidationError(
                f"Device target '{target_device_id}' is not a Home Assistant "
                "WLED device"
            )

        resolved_device = devices_by_ha_id.get(target_device_id)
        if resolved_device is None:
            raise WLEDValidationError(
                f"WLED device target '{target_device_id}' could not be "
                "resolved for backup"
            )

        resolved.append(resolved_device)

    return resolved


def _find_registry_device(
    registry: dr.DeviceRegistry,
    entry: ConfigEntry,
    mac: str | None,
) -> dr.DeviceEntry | None:
    """Find the registry device corresponding to a WLED config entry."""
    if mac is None:
        return None

    identifier = (WLED_DOMAIN, mac)
    connection = (dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac))

    scoped_identifier_lookup = getattr(registry, "async_get_device_by_identifier", None)
    if callable(scoped_identifier_lookup):
        try:
            device = scoped_identifier_lookup(identifier, entry.entry_id)
        except TypeError:
            device = None
        if device is not None:
            return device

    scoped_connection_lookup = getattr(registry, "async_get_device_by_connection", None)
    if callable(scoped_connection_lookup):
        try:
            device = scoped_connection_lookup(connection, entry.entry_id)
        except TypeError:
            device = None
        if device is not None:
            return device

    for identifiers, connections in (
        ({identifier}, None),
        (None, {connection}),
    ):
        device = registry.async_get_device(
            identifiers=identifiers,
            connections=connections,
        )
        if device is not None and _device_matches_entry(device, entry.entry_id):
            return device

    return None


def _device_matches_entry(device: dr.DeviceEntry, entry_id: str) -> bool:
    """Check whether a device registry entry belongs to a config entry."""
    config_entries = getattr(device, "config_entries", None)
    if config_entries is None:
        return True
    return entry_id in config_entries


def _is_wled_registry_device(hass: HomeAssistant, device: dr.DeviceEntry) -> bool:
    """Return whether a registry device belongs to a WLED config entry."""
    for entry_id in getattr(device, "config_entries", set()):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == WLED_DOMAIN:
            return True
    return False


def _extract_target_device_ids(call: ServiceCall | Any) -> list[str]:
    """Extract targeted HA device ids from a service call."""
    data = getattr(call, "data", {}) or {}
    raw_device_ids = data.get("device_id")
    if raw_device_ids is None and isinstance(data.get("target"), dict):
        raw_device_ids = data["target"].get("device_id")

    if raw_device_ids is None:
        return []
    if isinstance(raw_device_ids, str):
        return [raw_device_ids]
    if isinstance(raw_device_ids, (list, tuple, set)):
        return [str(device_id) for device_id in raw_device_ids]
    return [str(raw_device_ids)]


def _normalize_mac(mac: str | None) -> str | None:
    """Normalize MAC addresses to lowercase without separators."""
    if not mac:
        return None

    formatted = dr.format_mac(mac)
    if formatted:
        return formatted.replace(":", "")

    return re.sub(r"[^a-f0-9]", "", mac.lower()) or None


def _sanitize_host(host: str) -> str:
    """Build a stable fallback identifier from a host name or address."""
    normalized = re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_")
    return normalized or "unknown_host"