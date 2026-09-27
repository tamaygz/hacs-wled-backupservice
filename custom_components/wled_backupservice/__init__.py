"""Support for the WLED Backup Service integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .manager import WLEDBackupConfigEntry, WLEDBackupManager
from .services import async_register_services


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration domain and register services."""
    del config
    await async_register_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Set up the integration from a config entry."""
    manager = WLEDBackupManager(hass, entry)
    await manager.async_setup()
    typed_entry: WLEDBackupConfigEntry = entry
    typed_entry.runtime_data = manager
    typed_entry.async_on_unload(
        typed_entry.add_update_listener(_async_update_listener)
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: WLEDBackupConfigEntry
) -> bool:
    """Unload the integration config entry."""
    del hass
    await entry.runtime_data.async_shutdown()
    return True


async def async_migrate_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Migrate older config entries to the current version."""
    del hass, entry
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
