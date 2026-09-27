"""Service registration scaffold for the WLED Backup Service integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .discovery import WLEDDevice, async_resolve_target_devices
from .models import BackupResult, RestoreResult
from .retention import PruneResult
from .storage import StoredBackup

SERVICES_REGISTERED_KEY = f"{DOMAIN}_services_registered"
SERVICE_BACKUP = "backup"
SERVICE_BACKUP_ALL = "backup_all"
SERVICE_RESTORE = "restore"
SERVICE_LIST_BACKUPS = "list_backups"
SERVICE_DELETE_BACKUP = "delete_backup"
SERVICE_PRUNE = "prune"
SERVICE_DISCOVER = "discover"

BACKUP_SCHEMA = vol.Schema(
    {
        vol.Optional("include_presets"): bool,
        vol.Optional("include_state"): bool,
        vol.Optional("label"): str,
        vol.Optional("device_id"): vol.Any(str, [str]),
    },
    extra=vol.ALLOW_EXTRA,
)
BACKUP_ALL_SCHEMA = vol.Schema(
    {
        vol.Optional("include_presets"): bool,
        vol.Optional("include_state"): bool,
    },
    extra=vol.ALLOW_EXTRA,
)
RESTORE_SCHEMA = vol.Schema(
    {
        vol.Required("backup_id"): str,
        vol.Optional("backup_before_restore"): bool,
        vol.Optional("restore_config"): bool,
        vol.Optional("restore_presets"): bool,
        vol.Optional("verify_after_restore"): bool,
        vol.Optional("reboot_after_restore"): bool,
        vol.Optional("device_id"): vol.Any(str, [str]),
    },
    extra=vol.ALLOW_EXTRA,
)
LIST_BACKUPS_SCHEMA = vol.Schema(
    {
        vol.Optional("limit"): vol.All(int, vol.Range(min=1)),
        vol.Optional("device_id"): vol.Any(str, [str]),
    },
    extra=vol.ALLOW_EXTRA,
)
DELETE_BACKUP_SCHEMA = vol.Schema(
    {vol.Required("backup_id"): str},
    extra=vol.ALLOW_EXTRA,
)
PRUNE_SCHEMA = vol.Schema(
    {
        vol.Optional("dry_run"): bool,
        vol.Optional("device_id"): vol.Any(str, [str]),
    },
    extra=vol.ALLOW_EXTRA,
)
DISCOVER_SCHEMA = vol.Schema({}, extra=vol.ALLOW_EXTRA)


async def async_register_services(hass: HomeAssistant) -> None:
    """Register integration services exactly once."""
    if hass.services.has_service(DOMAIN, SERVICE_BACKUP):
        hass.data[SERVICES_REGISTERED_KEY] = True
        return

    async def handle_backup(call: ServiceCall) -> dict[str, Any]:
        manager = _get_loaded_manager(hass)
        devices = await _resolve_devices_or_raise(hass, call, required=True)
        results = []
        for device in devices:
            result = await manager.async_backup_device(
                device,
                include_presets=call.data.get("include_presets"),
                include_state=call.data.get("include_state"),
                label=call.data.get("label"),
            )
            results.append(_serialize_backup_result(result))
        return {"results": results}

    async def handle_backup_all(call: ServiceCall) -> dict[str, Any]:
        manager = _get_loaded_manager(hass)
        results = await manager.async_backup_all(
            include_presets=call.data.get("include_presets"),
            include_state=call.data.get("include_state"),
        )
        return {"results": [_serialize_backup_result(item) for item in results]}

    async def handle_restore(call: ServiceCall) -> dict[str, Any] | None:
        manager = _get_loaded_manager(hass)
        devices = await _resolve_devices_or_raise(hass, call, required=True)
        if len(devices) != 1:
            raise ServiceValidationError(
                "restore requires exactly one WLED target device"
            )

        try:
            response = await manager.async_restore(
                devices[0],
                backup_id=call.data["backup_id"],
                backup_before_restore=call.data.get("backup_before_restore"),
                restore_config=call.data.get("restore_config"),
                restore_presets=call.data.get("restore_presets"),
                verify_after_restore=call.data.get("verify_after_restore"),
                reboot_after_restore=call.data.get("reboot_after_restore"),
            )
        except NotImplementedError as err:
            raise HomeAssistantError(
                "Restore is not available until the restore engine is implemented"
            ) from err
        if isinstance(response, RestoreResult):
            return _serialize_restore_result(response)
        return response

    async def handle_list_backups(call: ServiceCall) -> dict[str, Any]:
        manager = _get_loaded_manager(hass)
        devices = await _resolve_devices_or_raise(hass, call, required=False)

        if not devices:
            backups = await manager.async_list_backups(limit=call.data.get("limit"))
        else:
            backups = []
            limit = call.data.get("limit")
            for device in devices:
                backups.extend(
                    await manager.async_list_backups(device=device, limit=limit)
                )
            backups.sort(key=lambda backup: backup.created_at, reverse=True)
            if limit is not None:
                backups = backups[: int(limit)]

        return {"backups": [_serialize_stored_backup(item) for item in backups]}

    async def handle_delete_backup(call: ServiceCall) -> dict[str, Any]:
        manager = _get_loaded_manager(hass)
        await manager.async_delete_backup(backup_id=call.data["backup_id"])
        return {"deleted": [call.data["backup_id"]]}

    async def handle_prune(call: ServiceCall) -> dict[str, Any]:
        manager = _get_loaded_manager(hass)
        devices = await _resolve_devices_or_raise(hass, call, required=False)

        if not devices:
            result = await manager.async_prune(dry_run=call.data.get("dry_run", False))
        elif len(devices) == 1:
            result = await manager.async_prune(
                device=devices[0],
                dry_run=call.data.get("dry_run", False),
            )
        else:
            device_results = []
            for device in devices:
                partial = await manager.async_prune(
                    device=device,
                    dry_run=call.data.get("dry_run", False),
                )
                device_results.extend(partial.device_results)
            result = PruneResult(
                dry_run=bool(call.data.get("dry_run", False)),
                device_results=tuple(device_results),
            )

        return _serialize_prune_result(result)

    async def handle_discover(call: ServiceCall) -> dict[str, Any]:
        del call
        manager = _get_loaded_manager(hass)
        devices = await manager.async_discover_devices()
        return {"devices": [_serialize_wled_device(device) for device in devices]}

    hass.services.async_register(
        DOMAIN,
        SERVICE_BACKUP,
        handle_backup,
        schema=BACKUP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_BACKUP_ALL,
        handle_backup_all,
        schema=BACKUP_ALL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTORE,
        handle_restore,
        schema=RESTORE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_BACKUPS,
        handle_list_backups,
        schema=LIST_BACKUPS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_BACKUP,
        handle_delete_backup,
        schema=DELETE_BACKUP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PRUNE,
        handle_prune,
        schema=PRUNE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DISCOVER,
        handle_discover,
        schema=DISCOVER_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.data[SERVICES_REGISTERED_KEY] = True


def _get_loaded_manager(hass: HomeAssistant) -> Any:
    """Return the loaded manager from the single config entry."""
    entries: list[ConfigEntry] = list(hass.config_entries.async_entries(DOMAIN))
    if not entries:
        raise HomeAssistantError(
            "No WLED Backup Service config entry is currently loaded"
        )

    manager = getattr(entries[0], "runtime_data", None)
    if manager is None:
        raise HomeAssistantError(
            "WLED Backup Service is not ready yet; load the config entry first"
        )
    return manager


async def _resolve_devices_or_raise(
    hass: HomeAssistant,
    call: ServiceCall,
    *,
    required: bool,
) -> list[WLEDDevice]:
    """Resolve targeted devices and optionally require at least one."""
    devices = await async_resolve_target_devices(hass, call)
    if required and not devices:
        raise ServiceValidationError(
            "This action requires at least one WLED device target"
        )
    return devices


def _serialize_backup_result(result: BackupResult) -> dict[str, Any]:
    """Convert a backup result into a JSON-serializable response payload."""
    return {
        "device_id": result.device_id,
        "device_name": result.device_name,
        "success": result.success,
        "backup_id": result.backup_id,
        "path": str(result.path) if result.path is not None else None,
        "files": list(result.files),
        "created_at": result.created_at.isoformat() if result.created_at else None,
        "error": result.error,
    }


def _serialize_stored_backup(backup: StoredBackup) -> dict[str, Any]:
    """Convert a stored backup descriptor into response data."""
    return {
        "backup_id": backup.backup_id,
        "path": str(backup.path),
        "created_at": backup.created_at.isoformat(),
        "integration_version": backup.integration_version,
        "device": {
            "name": backup.device.name,
            "host": backup.device.host,
            "mac": backup.device.mac,
            "device_id": backup.device.device_id,
            "firmware_version": backup.device.firmware_version,
        },
        "files": [
            {"name": file.name, "size": file.size, "sha256": file.sha256}
            for file in backup.files
        ],
    }


def _serialize_prune_result(result: PruneResult) -> dict[str, Any]:
    """Convert a prune result into a JSON-serializable response payload."""
    return {
        "dry_run": result.dry_run,
        "device_results": [
            {
                "device_id": item.device_id,
                "total_backups": item.total_backups,
                "kept_backup_ids": list(item.kept_backup_ids),
                "would_delete_backup_ids": list(item.would_delete_backup_ids),
                "deleted_backup_ids": list(item.deleted_backup_ids),
                "failed_backup_ids": list(item.failed_backup_ids),
            }
            for item in result.device_results
        ],
    }


def _serialize_wled_device(device: WLEDDevice) -> dict[str, Any]:
    """Convert a discovered WLED device into response data."""
    return {
        "device_id": device.device_id,
        "name": device.name,
        "host": device.host,
        "mac": device.mac,
        "ha_device_id": device.ha_device_id,
        "ha_config_entry_id": device.ha_config_entry_id,
        "firmware_version": device.firmware_version,
    }


def _serialize_restore_result(result: RestoreResult) -> dict[str, Any]:
    """Convert a restore result into a JSON-serializable response payload."""
    return {
        "device_id": result.device_id,
        "device_name": result.device_name,
        "backup_id": result.backup_id,
        "success": result.success,
        "safety_backup_id": result.safety_backup_id,
        "config_status": result.config_status,
        "presets_status": result.presets_status,
        "verification_status": result.verification_status,
        "rebooted": result.rebooted,
        "firmware_mismatch": result.firmware_mismatch,
        "messages": list(result.messages),
        "error": result.error,
    }