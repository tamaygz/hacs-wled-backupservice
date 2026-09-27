"""Service registration scaffold for the WLED Backup Service integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import DOMAIN

SERVICES_REGISTERED_KEY = f"{DOMAIN}_services_registered"


async def async_register_services(hass: HomeAssistant) -> None:
    """Register integration services exactly once."""
    if hass.data.get(SERVICES_REGISTERED_KEY):
        return
    hass.data[SERVICES_REGISTERED_KEY] = True