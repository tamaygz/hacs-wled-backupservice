"""Lifecycle manager shell for the WLED Backup Service integration."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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

    async def async_backup_device(self, *args: Any, **kwargs: Any) -> Any:
        """Back up a single WLED device."""
        raise NotImplementedError

    async def async_backup_all(self, *args: Any, **kwargs: Any) -> Any:
        """Back up all discovered WLED devices."""
        raise NotImplementedError

    async def async_restore(self, *args: Any, **kwargs: Any) -> Any:
        """Restore a WLED device backup."""
        raise NotImplementedError

    async def async_list_backups(self, *args: Any, **kwargs: Any) -> Any:
        """List available backups."""
        raise NotImplementedError

    async def async_delete_backup(self, *args: Any, **kwargs: Any) -> Any:
        """Delete a backup."""
        raise NotImplementedError

    async def async_prune(self, *args: Any, **kwargs: Any) -> Any:
        """Prune old backups."""
        raise NotImplementedError

    async def async_discover_devices(self, *args: Any, **kwargs: Any) -> Any:
        """Discover WLED devices."""
        raise NotImplementedError