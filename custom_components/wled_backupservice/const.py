"""Constants for the WLED Backup Service integration."""

from __future__ import annotations

import logging

DOMAIN = "wled_backupservice"
NAME = "WLED Backup Service"
LOGGER = logging.getLogger(__package__)

WLED_DOMAIN = "wled"

CONF_SCHEDULE_ENABLED = "schedule_enabled"
CONF_INTERVAL = "interval"
CONF_INTERVAL_UNIT = "interval_unit"
CONF_DAILY_TIME = "daily_time"
CONF_STORAGE_ROOT = "storage_root"
CONF_SUBDIR = "subdir"
CONF_INCLUDE_PRESETS = "include_presets"
CONF_INCLUDE_STATE = "include_state"
CONF_CREATE_ARCHIVE = "create_archive"
CONF_RETENTION_COUNT = "retention_count"
CONF_RETENTION_DAYS = "retention_days"
CONF_BACKUP_BEFORE_RESTORE = "backup_before_restore"
CONF_VERIFY_AFTER_RESTORE = "verify_after_restore"
CONF_REBOOT_AFTER_RESTORE = "reboot_after_restore"

INTERVAL_UNIT_MINUTES = "minutes"
INTERVAL_UNIT_HOURS = "hours"
INTERVAL_UNIT_DAYS = "days"
INTERVAL_UNITS = (
    INTERVAL_UNIT_MINUTES,
    INTERVAL_UNIT_HOURS,
    INTERVAL_UNIT_DAYS,
)

DEFAULT_SCHEDULE_ENABLED = True
DEFAULT_INTERVAL = 24
DEFAULT_INTERVAL_UNIT = INTERVAL_UNIT_HOURS
DEFAULT_DAILY_TIME = "00:00:00"
DEFAULT_STORAGE_ROOT = "share"
DEFAULT_SUBDIR = "wled_backups"
DEFAULT_INCLUDE_PRESETS = True
DEFAULT_INCLUDE_STATE = False
DEFAULT_CREATE_ARCHIVE = False
DEFAULT_RETENTION_COUNT = 30
DEFAULT_RETENTION_DAYS = 0
DEFAULT_BACKUP_BEFORE_RESTORE = True
DEFAULT_VERIFY_AFTER_RESTORE = True
DEFAULT_REBOOT_AFTER_RESTORE = False

# The /config entry is symbolic here.
# Resolve it with hass.config.path() at runtime.
STORAGE_ROOTS = {
    "share": "/share",
    "media": "/media",
    "backup": "/backup",
    "config": "/config",
}

BACKUP_SCHEMA_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
CFG_FILENAME = "cfg.json"
PRESETS_FILENAME = "presets.json"
STATE_FILENAME = "state.json"
INFO_FILENAME = "info.json"