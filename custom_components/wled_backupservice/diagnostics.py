"""Diagnostics support for the WLED Backup Service integration."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_STORAGE_ROOT, CONF_SUBDIR, DEFAULT_STORAGE_ROOT, DEFAULT_SUBDIR
from .manager import INTEGRATION_VERSION, WLEDBackupManager

TO_REDACT = {"host", "mac", "device_id", "token", "password", "api_key"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    del hass
    manager = getattr(entry, "runtime_data", None)

    diagnostics: dict[str, Any] = {
        "integration": {
            "domain": entry.domain,
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": getattr(manager, "integration_version", INTEGRATION_VERSION),
        },
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "storage": {
            "root_type": entry.options.get(CONF_STORAGE_ROOT, DEFAULT_STORAGE_ROOT),
            "subdir": entry.options.get(CONF_SUBDIR, DEFAULT_SUBDIR),
        },
    }

    if not isinstance(manager, WLEDBackupManager):
        diagnostics["runtime"] = {
            "loaded": False,
            "is_setup": False,
            "is_shutdown": True,
            "scheduler_registered": False,
            "scheduled_cycle_in_progress": False,
            "discovered_device_count": 0,
            "last_backup_status": None,
            "last_backup_success": None,
            "last_error": None,
        }
        diagnostics["devices"] = []
        diagnostics["backups"] = {"total_count": 0, "by_device": []}
        return diagnostics

    diagnostics["runtime"] = {
        "loaded": True,
        "is_setup": manager.is_setup,
        "is_shutdown": manager.is_shutdown,
        "scheduler_registered": manager.scheduler_unsub is not None,
        "scheduled_cycle_in_progress": bool(
            manager.scheduled_cycle_task is not None
            and not manager.scheduled_cycle_task.done()
        ),
        "discovered_device_count": manager.discovered_device_count,
        "last_backup_status": manager.last_backup_status,
        "last_backup_success": (
            manager.last_backup_success.isoformat()
            if manager.last_backup_success is not None
            else None
        ),
        "last_error": manager.last_error,
    }

    devices: list[Any] = []
    backups: list[Any] = []

    try:
        devices = await manager.async_discover_devices()
    except Exception as err:
        diagnostics["discovery_error"] = str(err)

    try:
        backups = await manager.async_list_backups()
    except Exception as err:
        diagnostics["backup_inventory_error"] = str(err)

    backup_counts = Counter(backup.device.device_id for backup in backups)
    latest_backup_by_device = {
        backup.device.device_id: backup.created_at.isoformat() for backup in backups
    }

    diagnostics["devices"] = [
        {
            "name": device.name,
            "firmware_version": device.firmware_version,
            "host_masked": _mask_value(device.host),
            "mac_masked": _mask_value(device.mac),
            "device_id_masked": _mask_value(device.device_id),
            "backup_count": backup_counts.get(device.device_id, 0),
            "latest_backup_at": latest_backup_by_device.get(device.device_id),
        }
        for device in devices
    ]
    diagnostics["backups"] = {
        "total_count": len(backups),
        "by_device": [
            {
                "name": backup.device.name,
                "firmware_version": backup.device.firmware_version,
                "host_masked": _mask_value(backup.device.host),
                "mac_masked": _mask_value(backup.device.mac),
                "device_id_masked": _mask_value(backup.device.device_id),
                "backup_id": backup.backup_id,
                "created_at": backup.created_at.isoformat(),
                "integration_version": backup.integration_version,
            }
            for backup in backups
        ],
    }
    return diagnostics


def _mask_value(value: str | None) -> str | None:
    """Partially mask a value for useful-but-safe diagnostics."""
    if value in (None, ""):
        return value
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    return f"{text[:2]}***{text[-2:]}"