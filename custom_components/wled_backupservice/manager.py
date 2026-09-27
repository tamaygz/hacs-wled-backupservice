"""Lifecycle manager shell for the WLED Backup Service integration."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CFG_FILENAME,
    CONF_BACKUP_BEFORE_RESTORE,
    CONF_INCLUDE_PRESETS,
    CONF_INCLUDE_STATE,
    CONF_REBOOT_AFTER_RESTORE,
    CONF_RETENTION_COUNT,
    CONF_RETENTION_DAYS,
    CONF_STORAGE_ROOT,
    CONF_SUBDIR,
    CONF_VERIFY_AFTER_RESTORE,
    DEFAULT_BACKUP_BEFORE_RESTORE,
    DEFAULT_INCLUDE_PRESETS,
    DEFAULT_INCLUDE_STATE,
    DEFAULT_REBOOT_AFTER_RESTORE,
    DEFAULT_RETENTION_COUNT,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_STORAGE_ROOT,
    DEFAULT_SUBDIR,
    DEFAULT_VERIFY_AFTER_RESTORE,
    INFO_FILENAME,
    LOGGER,
    PRESETS_FILENAME,
    STATE_FILENAME,
)
from .exceptions import WLEDBackupError, WLEDRestoreError, WLEDValidationError
from .models import BackupResult, RestoreResult

if TYPE_CHECKING:
    WLEDBackupConfigEntry: TypeAlias = ConfigEntry["WLEDBackupManager"]
else:
    WLEDBackupConfigEntry = ConfigEntry


class WLEDBackupManager:
    """Composition root for integration runtime objects."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the manager shell."""
        self.hass = hass
        self.entry = entry
        self.discovery: Any | None = None
        self.client_factory: Any | None = None
        self.storage: Any | None = None
        self.retention: Any | None = None
        self.scheduler_unsub: Any | None = None
        self.locks: dict[str, asyncio.Lock] = {}
        self.is_setup = False
        self.is_shutdown = False

    async def async_setup(self) -> None:
        """Set up manager state."""
        self.is_setup = True
        self.is_shutdown = False

    async def async_shutdown(self) -> None:
        """Tear down manager state."""
        self.is_shutdown = True
        self.scheduler_unsub = None

    async def async_backup_device(
        self,
        device: Any,
        *,
        include_presets: bool | None = None,
        include_state: bool | None = None,
        label: str | None = None,
    ) -> BackupResult:
        """Back up a single WLED device."""
        del label
        await self._async_ensure_discovery()
        self._ensure_client_factory()
        self._ensure_storage()

        lock = self._async_get_device_lock(device.device_id)
        async with lock:
            include_presets_value = self._bool_option(
                CONF_INCLUDE_PRESETS,
                DEFAULT_INCLUDE_PRESETS,
                include_presets,
            )
            include_state_value = self._bool_option(
                CONF_INCLUDE_STATE,
                DEFAULT_INCLUDE_STATE,
                include_state,
            )

            try:
                client_factory = self.client_factory
                storage = self.storage
                assert client_factory is not None
                assert storage is not None

                client = client_factory(device.host)
                info = await client.async_get_info()
                self._validate_verified_info(device, info)

                files = {
                    CFG_FILENAME: self._json_bytes(await client.async_get_config()),
                    INFO_FILENAME: self._json_bytes(asdict(info)),
                }
                if include_presets_value:
                    files[PRESETS_FILENAME] = await client.async_get_presets_raw()
                if include_state_value:
                    files[STATE_FILENAME] = self._json_bytes(
                        await client.async_get_state()
                    )

                verified_mac = device.mac or info.mac_address
                verified_device_id = (
                    info.device_id or info.mac_address or device.device_id
                )
                if device.mac and info.mac_address and info.mac_address != device.mac:
                    LOGGER.warning(
                        "Discovered MAC %s for %s differs from verified MAC %s",
                        device.mac,
                        device.name,
                        info.mac_address,
                    )

                backup = await storage.async_write_backup(
                    device_name=device.name,
                    host=device.host,
                    device_id=verified_device_id,
                    mac=verified_mac,
                    firmware_version=info.version,
                    files=files,
                )
                result = BackupResult(
                    device_id=backup.device.device_id,
                    device_name=backup.device.name,
                    success=True,
                    backup_id=backup.backup_id,
                    path=backup.path,
                    files=tuple(file_record.name for file_record in backup.files),
                    created_at=backup.created_at,
                    error=None,
                )
                LOGGER.info(
                    "Created WLED backup for %s at %s",
                    device.name,
                    backup.backup_id,
                )
                return result
            except WLEDBackupError as err:
                LOGGER.warning("Backup failed for %s: %s", device.name, err)
                return BackupResult(
                    device_id=device.device_id,
                    device_name=device.name,
                    success=False,
                    backup_id=None,
                    path=None,
                    files=(),
                    created_at=None,
                    error=str(err),
                )

    async def async_backup_all(
        self,
        *,
        include_presets: bool | None = None,
        include_state: bool | None = None,
    ) -> list[BackupResult]:
        """Back up all discovered WLED devices."""
        devices = await self.async_discover_devices()
        LOGGER.info("Starting WLED backup cycle for %s devices", len(devices))

        results: list[BackupResult] = []
        for device in devices:
            result = await self.async_backup_device(
                device,
                include_presets=include_presets,
                include_state=include_state,
            )
            results.append(result)
        LOGGER.info("Finished WLED backup cycle for %s devices", len(devices))
        return results

    async def async_restore(self, *args: Any, **kwargs: Any) -> Any:
        """Restore a WLED device backup."""
        device = args[0] if args else kwargs.pop("device")
        backup_id = str(kwargs.pop("backup_id"))
        backup_before_restore = self._bool_option(
            CONF_BACKUP_BEFORE_RESTORE,
            DEFAULT_BACKUP_BEFORE_RESTORE,
            kwargs.pop("backup_before_restore", None),
        )
        restore_config = bool(kwargs.pop("restore_config", True))
        restore_presets = bool(kwargs.pop("restore_presets", True))
        verify_after_restore = self._bool_option(
            CONF_VERIFY_AFTER_RESTORE,
            DEFAULT_VERIFY_AFTER_RESTORE,
            kwargs.pop("verify_after_restore", None),
        )
        reboot_after_restore = self._bool_option(
            CONF_REBOOT_AFTER_RESTORE,
            DEFAULT_REBOOT_AFTER_RESTORE,
            kwargs.pop("reboot_after_restore", None),
        )
        if kwargs:
            raise TypeError(f"Unexpected restore kwargs: {sorted(kwargs)}")

        self._ensure_client_factory()
        self._ensure_storage()
        client_factory = self.client_factory
        storage = self.storage
        assert client_factory is not None
        assert storage is not None

        lock = self._async_get_device_lock(device.device_id)
        async with lock:
            descriptor = await storage.async_read_backup(backup_id)
            client = client_factory(device.host)
            info = await client.async_get_info()
            self._validate_verified_info(device, info)

            if (
                descriptor.device.mac
                and info.mac_address
                and descriptor.device.mac != info.mac_address
            ):
                raise WLEDRestoreError(
                    f"Backup {backup_id!r} belongs to {descriptor.device.mac}, "
                    f"not {info.mac_address}"
                )

            messages: list[str] = []
            firmware_mismatch = False
            if (
                descriptor.device.firmware_version is not None
                and descriptor.device.firmware_version != info.version
            ):
                firmware_mismatch = True
                messages.append(
                    f"Backup firmware {descriptor.device.firmware_version} differs "
                    f"from device firmware {info.version}"
                )
                LOGGER.warning(messages[-1])

            safety_backup_id: str | None = None
            if backup_before_restore:
                safety_backup = await self.async_backup_device(device)
                if not safety_backup.success or safety_backup.backup_id is None:
                    raise WLEDRestoreError(
                        f"Safety backup failed for {device.name}: "
                        f"{safety_backup.error or 'unknown error'}"
                    )
                safety_backup_id = safety_backup.backup_id

            config_status = "skipped"
            presets_status = "skipped"
            verification_status = "skipped"
            rebooted = False

            if restore_config:
                cfg_bytes = await storage.async_read_backup_file(
                    backup_id,
                    CFG_FILENAME,
                )
                cfg_payload = json.loads(cfg_bytes.decode("utf-8"))
                await client.async_set_config(cfg_payload)
                config_status = "ok"

            if restore_presets:
                if not (
                    client.capabilities.presets_upload_supported
                    and client.capabilities.presets_upload_verified
                ):
                    presets_status = "unsupported"
                    messages.append(
                        "Preset restore is unavailable until the upload path is "
                        "verified"
                    )
                else:
                    presets_bytes = await storage.async_read_backup_file(
                        backup_id,
                        PRESETS_FILENAME,
                    )
                    await client.async_upload_presets(presets_bytes)
                    presets_status = "ok"

            if reboot_after_restore and config_status == "ok":
                await client.async_reboot()
                rebooted = True

            if verify_after_restore:
                verification_status = "ok"
                if config_status == "ok":
                    expected_cfg = json.loads(
                        (
                            await storage.async_read_backup_file(
                                backup_id,
                                CFG_FILENAME,
                            )
                        ).decode("utf-8")
                    )
                    if await client.async_get_config() != expected_cfg:
                        verification_status = "failed"
                        messages.append("Config verification failed after restore")
                if presets_status == "ok":
                    expected_presets = await storage.async_read_backup_file(
                        backup_id,
                        PRESETS_FILENAME,
                    )
                    if await client.async_get_presets_raw() != expected_presets:
                        verification_status = "failed"
                        messages.append("Presets verification failed after restore")

            success = (
                config_status in {"ok", "skipped"}
                and presets_status in {"ok", "skipped", "unsupported"}
                and verification_status in {"ok", "skipped"}
            )

            if (
                not success
                and config_status != "ok"
                and presets_status not in {"ok", "unsupported", "skipped"}
            ):
                raise WLEDRestoreError(
                    f"Restore of {backup_id!r} failed for {device.name}"
                )

            return RestoreResult(
                device_id=device.device_id,
                device_name=device.name,
                backup_id=backup_id,
                success=success,
                safety_backup_id=safety_backup_id,
                config_status=config_status,
                presets_status=presets_status,
                verification_status=verification_status,
                rebooted=rebooted,
                firmware_mismatch=firmware_mismatch,
                messages=tuple(messages),
                error=(
                    None
                    if success
                    else "Restore completed with warnings or partial failure"
                ),
            )

    async def async_list_backups(self, *args: Any, **kwargs: Any) -> Any:
        """List available backups."""
        del args
        device = kwargs.pop("device", None)
        limit = kwargs.pop("limit", None)
        if kwargs:
            raise TypeError(f"Unexpected list_backups kwargs: {sorted(kwargs)}")

        self._ensure_storage()
        storage = self.storage
        assert storage is not None

        device_id = getattr(device, "device_id", device)
        backups = await storage.async_list(device_id)
        if limit is not None:
            backups = backups[: int(limit)]
        return backups

    async def async_delete_backup(self, *args: Any, **kwargs: Any) -> Any:
        """Delete a backup."""
        del args
        backup_id = kwargs.pop("backup_id")
        if kwargs:
            raise TypeError(f"Unexpected delete_backup kwargs: {sorted(kwargs)}")

        self._ensure_storage()
        storage = self.storage
        assert storage is not None
        await storage.async_delete(str(backup_id))

    async def async_prune(self, *args: Any, **kwargs: Any) -> Any:
        """Prune old backups."""
        del args
        device = kwargs.pop("device", None)
        dry_run = bool(kwargs.pop("dry_run", False))
        if kwargs:
            raise TypeError(f"Unexpected prune kwargs: {sorted(kwargs)}")

        self._ensure_storage()
        self._ensure_retention()
        storage = self.storage
        retention = self.retention
        assert storage is not None
        assert retention is not None
        return await retention.async_prune_backups(
            storage,
            retention_count=int(
                self.entry.options.get(
                    CONF_RETENTION_COUNT,
                    DEFAULT_RETENTION_COUNT,
                )
            ),
            retention_days=int(
                self.entry.options.get(
                    CONF_RETENTION_DAYS,
                    DEFAULT_RETENTION_DAYS,
                )
            ),
            device=device,
            dry_run=dry_run,
        )

    async def async_discover_devices(self, *args: Any, **kwargs: Any) -> Any:
        """Discover WLED devices."""
        del args, kwargs
        await self._async_ensure_discovery()
        discovery = self.discovery
        assert discovery is not None
        return await discovery.async_discover_wled_devices(self.hass)

    def _async_get_device_lock(self, device_id: str) -> asyncio.Lock:
        """Return the shared lock for a device, creating it lazily."""
        lock = self.locks.get(device_id)
        if lock is None:
            lock = asyncio.Lock()
            self.locks[device_id] = lock
        return lock

    async def _async_ensure_discovery(self) -> None:
        """Lazily wire the discovery collaborator."""
        if self.discovery is None:
            from . import discovery as discovery_module

            self.discovery = discovery_module

    def _ensure_client_factory(self) -> None:
        """Lazily wire the WLED client factory."""
        if self.client_factory is None:
            from .wled_client import WLEDClient

            session = async_get_clientsession(self.hass)
            self.client_factory = lambda host: WLEDClient(host, session)

    def _ensure_storage(self) -> None:
        """Lazily wire the backup storage collaborator."""
        if self.storage is None:
            from .storage import BackupStorage

            self.storage = BackupStorage(
                self.hass,
                storage_root=self.entry.options.get(
                    CONF_STORAGE_ROOT,
                    DEFAULT_STORAGE_ROOT,
                ),
                subdir=self.entry.options.get(CONF_SUBDIR, DEFAULT_SUBDIR),
            )

    def _ensure_retention(self) -> None:
        """Lazily wire the retention collaborator."""
        if self.retention is None:
            from . import retention as retention_module

            self.retention = retention_module

    def _bool_option(
        self,
        key: str,
        default: bool,
        override: bool | None,
    ) -> bool:
        """Resolve a boolean override against config-entry options."""
        if override is not None:
            return override
        return bool(self.entry.options.get(key, default))

    def _validate_verified_info(self, device: Any, info: Any) -> None:
        """Validate the basic identity returned by a live WLED info call."""
        if info.brand and info.brand != "WLED":
            raise WLEDValidationError(
                f"Expected WLED device at {device.host}, got {info.brand!r}"
            )
        if not (info.device_id or info.mac_address or device.mac):
            raise WLEDValidationError(
                f"WLED device at {device.host} did not report a usable identity"
            )

    def _json_bytes(self, payload: dict[str, Any]) -> bytes:
        """Serialize a JSON object to stable UTF-8 bytes for backup storage."""
        return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
