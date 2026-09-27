"""Config flow for the WLED Backup Service integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TimeSelector,
)

from .const import (
    CONF_BACKUP_BEFORE_RESTORE,
    CONF_CREATE_ARCHIVE,
    CONF_DAILY_TIME,
    CONF_INCLUDE_PRESETS,
    CONF_INCLUDE_STATE,
    CONF_INTERVAL,
    CONF_INTERVAL_UNIT,
    CONF_REBOOT_AFTER_RESTORE,
    CONF_RETENTION_COUNT,
    CONF_RETENTION_DAYS,
    CONF_SCHEDULE_ENABLED,
    CONF_STORAGE_ROOT,
    CONF_SUBDIR,
    CONF_VERIFY_AFTER_RESTORE,
    DEFAULT_BACKUP_BEFORE_RESTORE,
    DEFAULT_CREATE_ARCHIVE,
    DEFAULT_DAILY_TIME,
    DEFAULT_INCLUDE_PRESETS,
    DEFAULT_INCLUDE_STATE,
    DEFAULT_INTERVAL,
    DEFAULT_INTERVAL_UNIT,
    DEFAULT_REBOOT_AFTER_RESTORE,
    DEFAULT_RETENTION_COUNT,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_SCHEDULE_ENABLED,
    DEFAULT_STORAGE_ROOT,
    DEFAULT_SUBDIR,
    DEFAULT_VERIFY_AFTER_RESTORE,
    DOMAIN,
    INTERVAL_UNITS,
    NAME,
    STORAGE_ROOTS,
)
from .validators import normalize_backup_subdir

_SUPPORTS_OPTIONS_FLOW_CONFIG_ENTRY = hasattr(
    config_entries.OptionsFlow, "config_entry"
)


def _default_options() -> dict[str, Any]:
    """Build the default options stored on the config entry."""
    return {
        CONF_SCHEDULE_ENABLED: DEFAULT_SCHEDULE_ENABLED,
        CONF_INTERVAL: DEFAULT_INTERVAL,
        CONF_INTERVAL_UNIT: DEFAULT_INTERVAL_UNIT,
        CONF_DAILY_TIME: DEFAULT_DAILY_TIME,
        CONF_STORAGE_ROOT: DEFAULT_STORAGE_ROOT,
        CONF_SUBDIR: DEFAULT_SUBDIR,
        CONF_INCLUDE_PRESETS: DEFAULT_INCLUDE_PRESETS,
        CONF_INCLUDE_STATE: DEFAULT_INCLUDE_STATE,
        CONF_CREATE_ARCHIVE: DEFAULT_CREATE_ARCHIVE,
        CONF_RETENTION_COUNT: DEFAULT_RETENTION_COUNT,
        CONF_RETENTION_DAYS: DEFAULT_RETENTION_DAYS,
        CONF_BACKUP_BEFORE_RESTORE: DEFAULT_BACKUP_BEFORE_RESTORE,
        CONF_VERIFY_AFTER_RESTORE: DEFAULT_VERIFY_AFTER_RESTORE,
        CONF_REBOOT_AFTER_RESTORE: DEFAULT_REBOOT_AFTER_RESTORE,
    }


def _coerce_positive_int(value: Any) -> int:
    """Validate a strictly positive integer value."""
    coerced = int(value)
    if coerced <= 0:
        raise vol.Invalid("invalid_positive_int")
    return coerced


def _coerce_non_negative_int(value: Any) -> int:
    """Validate a non-negative integer value."""
    coerced = int(value)
    if coerced < 0:
        raise vol.Invalid("invalid_non_negative_int")
    return coerced


def _schedule_schema(options: Mapping[str, Any]) -> vol.Schema:
    """Build the schedule step schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_SCHEDULE_ENABLED,
                default=options[CONF_SCHEDULE_ENABLED],
            ): BooleanSelector(),
            vol.Required(CONF_INTERVAL, default=options[CONF_INTERVAL]): NumberSelector(
                NumberSelectorConfig(step=1, mode="box")
            ),
            vol.Required(
                CONF_INTERVAL_UNIT,
                default=options[CONF_INTERVAL_UNIT],
            ): SelectSelector(
                SelectSelectorConfig(
                    options=list(INTERVAL_UNITS),
                    translation_key=CONF_INTERVAL_UNIT,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_DAILY_TIME,
                default=options.get(CONF_DAILY_TIME, DEFAULT_DAILY_TIME),
            ): TimeSelector(),
        }
    )


def _storage_schema(options: Mapping[str, Any]) -> vol.Schema:
    """Build the storage step schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_STORAGE_ROOT,
                default=options[CONF_STORAGE_ROOT],
            ): SelectSelector(
                SelectSelectorConfig(
                    options=list(STORAGE_ROOTS),
                    translation_key=CONF_STORAGE_ROOT,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_SUBDIR, default=options[CONF_SUBDIR]): TextSelector(),
        }
    )


def _contents_schema(options: Mapping[str, Any]) -> vol.Schema:
    """Build the contents step schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_INCLUDE_PRESETS,
                default=options[CONF_INCLUDE_PRESETS],
            ): BooleanSelector(),
            vol.Required(
                CONF_INCLUDE_STATE,
                default=options[CONF_INCLUDE_STATE],
            ): BooleanSelector(),
            vol.Required(
                CONF_CREATE_ARCHIVE,
                default=options[CONF_CREATE_ARCHIVE],
            ): BooleanSelector(),
        }
    )


def _retention_schema(options: Mapping[str, Any]) -> vol.Schema:
    """Build the retention step schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_RETENTION_COUNT,
                default=options[CONF_RETENTION_COUNT],
            ): NumberSelector(NumberSelectorConfig(min=0, step=1, mode="box")),
            vol.Required(
                CONF_RETENTION_DAYS,
                default=options[CONF_RETENTION_DAYS],
            ): NumberSelector(NumberSelectorConfig(min=0, step=1, mode="box")),
        }
    )


def _behavior_schema(options: Mapping[str, Any]) -> vol.Schema:
    """Build the behavior step schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_BACKUP_BEFORE_RESTORE,
                default=options[CONF_BACKUP_BEFORE_RESTORE],
            ): BooleanSelector(),
            vol.Required(
                CONF_VERIFY_AFTER_RESTORE,
                default=options[CONF_VERIFY_AFTER_RESTORE],
            ): BooleanSelector(),
            vol.Required(
                CONF_REBOOT_AFTER_RESTORE,
                default=options[CONF_REBOOT_AFTER_RESTORE],
            ): BooleanSelector(),
        }
    )


class WLEDBackupServiceConfigFlow(  # type: ignore[call-arg]
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for the WLED Backup Service integration."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow handler for this config entry."""
        if _SUPPORTS_OPTIONS_FLOW_CONFIG_ENTRY:
            return _AutoInjectedWLEDBackupOptionsFlow()
        return WLEDBackupOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the single-instance user setup flow."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title=NAME,
                data={},
                options=_default_options(),
            )

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))


class _WLEDBackupOptionsFlowMixin:
    """Shared implementation for the WLED Backup Service options flow."""

    config_entry: ConfigEntry

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: vol.Schema,
        errors: dict[str, str] | None = None,
        description_placeholders: Mapping[str, str] | None = None,
    ) -> FlowResult:
        """Type stub provided by Home Assistant flow base classes."""
        raise NotImplementedError

    def async_create_entry(
        self,
        *,
        title: str | None = None,
        data: Mapping[str, Any],
        description: str | None = None,
        description_placeholders: Mapping[str, str] | None = None,
    ) -> FlowResult:
        """Type stub provided by Home Assistant flow base classes."""
        raise NotImplementedError

    def _initialize_options(self) -> None:
        """Initialize mutable options state for the multi-step flow."""
        self._options: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start the multi-step options flow."""
        self._options = {**_default_options(), **dict(self.config_entry.options)}
        return await self.async_step_schedule()

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle schedule-related options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                interval = _coerce_positive_int(user_input[CONF_INTERVAL])
            except (TypeError, ValueError, vol.Invalid):
                errors[CONF_INTERVAL] = "invalid_interval"
            else:
                self._options.update(
                    {
                        CONF_SCHEDULE_ENABLED: bool(user_input[CONF_SCHEDULE_ENABLED]),
                        CONF_INTERVAL: interval,
                        CONF_INTERVAL_UNIT: str(user_input[CONF_INTERVAL_UNIT]),
                        CONF_DAILY_TIME: user_input.get(CONF_DAILY_TIME)
                        or DEFAULT_DAILY_TIME,
                    }
                )
                return await self.async_step_storage()

        return self.async_show_form(
            step_id="schedule",
            data_schema=_schedule_schema(self._options),
            errors=errors,
        )

    async def async_step_storage(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle storage-related options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized_subdir = normalize_backup_subdir(
                    str(user_input[CONF_SUBDIR])
                )
            except vol.Invalid:
                errors[CONF_SUBDIR] = "invalid_subdir"
            else:
                self._options.update(
                    {
                        CONF_STORAGE_ROOT: str(user_input[CONF_STORAGE_ROOT]),
                        CONF_SUBDIR: normalized_subdir,
                    }
                )
                return await self.async_step_contents()

        return self.async_show_form(
            step_id="storage",
            data_schema=_storage_schema(self._options),
            errors=errors,
        )

    async def async_step_contents(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle backup-contents options."""
        if user_input is not None:
            self._options.update(
                {
                    CONF_INCLUDE_PRESETS: bool(user_input[CONF_INCLUDE_PRESETS]),
                    CONF_INCLUDE_STATE: bool(user_input[CONF_INCLUDE_STATE]),
                    CONF_CREATE_ARCHIVE: bool(user_input[CONF_CREATE_ARCHIVE]),
                }
            )
            return await self.async_step_retention()

        return self.async_show_form(
            step_id="contents",
            data_schema=_contents_schema(self._options),
        )

    async def async_step_retention(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle retention-related options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                retention_count = _coerce_non_negative_int(
                    user_input[CONF_RETENTION_COUNT]
                )
            except (TypeError, ValueError, vol.Invalid):
                errors[CONF_RETENTION_COUNT] = "invalid_retention_count"

            try:
                retention_days = _coerce_non_negative_int(
                    user_input[CONF_RETENTION_DAYS]
                )
            except (TypeError, ValueError, vol.Invalid):
                errors[CONF_RETENTION_DAYS] = "invalid_retention_days"

            if not errors:
                self._options.update(
                    {
                        CONF_RETENTION_COUNT: retention_count,
                        CONF_RETENTION_DAYS: retention_days,
                    }
                )
                return await self.async_step_behavior()

        return self.async_show_form(
            step_id="retention",
            data_schema=_retention_schema(self._options),
            errors=errors,
        )

    async def async_step_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle restore-behavior options."""
        if user_input is not None:
            self._options.update(
                {
                    CONF_BACKUP_BEFORE_RESTORE: bool(
                        user_input[CONF_BACKUP_BEFORE_RESTORE]
                    ),
                    CONF_VERIFY_AFTER_RESTORE: bool(
                        user_input[CONF_VERIFY_AFTER_RESTORE]
                    ),
                    CONF_REBOOT_AFTER_RESTORE: bool(
                        user_input[CONF_REBOOT_AFTER_RESTORE]
                    ),
                }
            )
            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="behavior",
            data_schema=_behavior_schema(self._options),
        )


class _AutoInjectedWLEDBackupOptionsFlow(
    config_entries.OptionsFlow,
    _WLEDBackupOptionsFlowMixin,
):
    """Handle options for HA versions with auto-injected config entries."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        super().__init__()
        self._initialize_options()


class WLEDBackupOptionsFlow(
    config_entries.OptionsFlowWithConfigEntry,
    _WLEDBackupOptionsFlowMixin,
):
    """Handle options for legacy HA versions requiring a config entry."""

    def __init__(self, config_entry: ConfigEntry | None = None) -> None:
        """Initialize the options flow."""
        if config_entry is None:
            raise ValueError(
                "config_entry is required on this Home Assistant version"
            )
        super().__init__(config_entry)
        self._initialize_options()