"""Custom exceptions for the WLED Backup Service integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class WLEDBackupError(HomeAssistantError):
    """Base error for WLED Backup Service failures."""


class WLEDConnectionError(WLEDBackupError):
    """Raised when communication with a WLED device fails."""


class WLEDValidationError(WLEDBackupError):
    """Raised when user input or device data fails validation."""


class WLEDBackupNotFoundError(WLEDBackupError):
    """Raised when a requested backup cannot be found."""


class WLEDRestoreError(WLEDBackupError):
    """Raised when a restore operation fails."""


class WLEDStorageError(WLEDBackupError):
    """Raised when filesystem storage operations fail."""


class WLEDDiscoveryError(WLEDBackupError):
    """Raised when WLED device discovery fails."""