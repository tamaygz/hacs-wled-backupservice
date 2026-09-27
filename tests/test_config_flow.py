"""Tests for the WLED Backup Service config and options flows."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wled_backupservice.config_flow import (
    _SUPPORTS_OPTIONS_FLOW_CONFIG_ENTRY,
    WLEDBackupOptionsFlow,
    WLEDBackupServiceConfigFlow,
    _schedule_schema,
)
from custom_components.wled_backupservice.const import (
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
    NAME,
)
from custom_components.wled_backupservice.validators import normalize_backup_subdir


def _default_options() -> dict[str, Any]:
    """Return the expected default options for a new config entry."""
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


def _make_options_flow(options: dict[str, Any] | None = None) -> WLEDBackupOptionsFlow:
    """Create a legacy-compatible options flow for direct step tests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options=options or _default_options(),
    )
    return WLEDBackupOptionsFlow(entry)


async def _start_storage_step(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> dict[str, Any]:
    """Start the options flow and advance it to the storage step."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "schedule"

    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCHEDULE_ENABLED: True,
            CONF_INTERVAL: 24,
            CONF_INTERVAL_UNIT: "days",
            CONF_DAILY_TIME: "06:30:00",
        },
    )


async def _complete_options_flow(
    hass: HomeAssistant,
    flow_id: str,
) -> dict[str, Any]:
    """Drive the options flow from the contents step to completion."""
    result = await hass.config_entries.options.async_configure(
        flow_id,
        {
            CONF_INCLUDE_PRESETS: False,
            CONF_INCLUDE_STATE: True,
            CONF_CREATE_ARCHIVE: True,
        },
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "retention"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_RETENTION_COUNT: 12,
            CONF_RETENTION_DAYS: 45,
        },
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "behavior"

    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_BACKUP_BEFORE_RESTORE: False,
            CONF_VERIFY_AFTER_RESTORE: False,
            CONF_REBOOT_AFTER_RESTORE: True,
        },
    )


@pytest.mark.asyncio
async def test_user_flow_creates_single_entry_with_default_options(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """The integration should create a single config entry with seeded defaults."""
    _ = enable_custom_integrations

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.title == NAME
    assert entry.data == {}
    assert dict(entry.options) == _default_options()
    assert entry.version == WLEDBackupServiceConfigFlow.VERSION


@pytest.mark.asyncio
async def test_second_setup_attempt_aborts(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """A second config entry must be rejected."""
    _ = enable_custom_integrations
    MockConfigEntry(
        domain=DOMAIN,
        data={},
        options=_default_options(),
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.asyncio
async def test_options_flow_persists_values_and_triggers_reload(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """The multi-step options flow should save values and reload the entry."""
    _ = enable_custom_integrations

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=_default_options())
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    with patch.object(
        hass.config_entries,
        "async_reload",
        AsyncMock(return_value=True),
    ) as reload_mock:
        result = await _start_storage_step(hass, entry)
        assert result["type"] is data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "storage"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_STORAGE_ROOT: "backup",
                CONF_SUBDIR: "custom\\nested",
            },
        )
        assert result["type"] is data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "contents"

        result = await _complete_options_flow(hass, result["flow_id"])
        assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY

        await hass.async_block_till_done()
        reload_mock.assert_awaited_once_with(entry.entry_id)

    assert dict(entry.options) == {
        CONF_SCHEDULE_ENABLED: True,
        CONF_INTERVAL: 24,
        CONF_INTERVAL_UNIT: "days",
        CONF_DAILY_TIME: "06:30:00",
        CONF_STORAGE_ROOT: "backup",
        CONF_SUBDIR: "custom/nested",
        CONF_INCLUDE_PRESETS: False,
        CONF_INCLUDE_STATE: True,
        CONF_CREATE_ARCHIVE: True,
        CONF_RETENTION_COUNT: 12,
        CONF_RETENTION_DAYS: 45,
        CONF_BACKUP_BEFORE_RESTORE: False,
        CONF_VERIFY_AFTER_RESTORE: False,
        CONF_REBOOT_AFTER_RESTORE: True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_interval", [0, -1])
async def test_options_flow_rejects_invalid_interval(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    invalid_interval: int,
) -> None:
    """Schedule validation should reject non-positive intervals."""
    _ = enable_custom_integrations
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=_default_options())
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCHEDULE_ENABLED: True,
            CONF_INTERVAL: invalid_interval,
            CONF_INTERVAL_UNIT: "hours",
            CONF_DAILY_TIME: DEFAULT_DAILY_TIME,
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "schedule"
    assert result["errors"] == {CONF_INTERVAL: "invalid_interval"}


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_subdir", ["../x", "/abs", "C:\\x"])
async def test_options_flow_rejects_invalid_subdir(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    invalid_subdir: str,
) -> None:
    """Storage validation should reject traversal and absolute paths."""
    _ = enable_custom_integrations
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=_default_options())
    entry.add_to_hass(hass)

    result = await _start_storage_step(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_STORAGE_ROOT: "share",
            CONF_SUBDIR: invalid_subdir,
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "storage"
    assert result["errors"] == {CONF_SUBDIR: "invalid_subdir"}


def test_options_flow_factory_uses_local_compatibility_path() -> None:
    """The options-flow factory should match the installed HA capability surface."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=_default_options())

    flow = WLEDBackupServiceConfigFlow.async_get_options_flow(entry)

    assert isinstance(flow, WLEDBackupOptionsFlow)
    if _SUPPORTS_OPTIONS_FLOW_CONFIG_ENTRY:
        assert "config_entry" not in flow.__dict__
    else:
        assert isinstance(flow, config_entries.OptionsFlowWithConfigEntry)


def test_options_flow_factory_supports_auto_injected_branch() -> None:
    """The factory should support future HA versions.

    Newer Home Assistant versions inject config entries automatically.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=_default_options())
    sentinel = object()

    with patch(
        "custom_components.wled_backupservice.config_flow._SUPPORTS_OPTIONS_FLOW_CONFIG_ENTRY",
        True,
    ), patch(
        "custom_components.wled_backupservice.config_flow._AutoInjectedWLEDBackupOptionsFlow",
        return_value=sentinel,
    ) as flow_ctor:
        flow = WLEDBackupServiceConfigFlow.async_get_options_flow(entry)

    flow_ctor.assert_called_once_with()
    assert flow is sentinel


def test_legacy_options_flow_requires_config_entry() -> None:
    """Legacy Home Assistant versions still require a config entry."""
    with pytest.raises(ValueError, match="config_entry is required"):
        WLEDBackupOptionsFlow()


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("", DEFAULT_SUBDIR),
        ("nested\\child", "nested/child"),
        ("./folder", "folder"),
    ],
)
def test_normalize_backup_subdir_accepts_relative_paths(
    raw_value: str,
    expected: str,
) -> None:
    """The shared storage-path validator should normalize safe relative inputs."""
    assert normalize_backup_subdir(raw_value) == expected


def test_schedule_schema_defaults_daily_time_when_missing() -> None:
    """The schedule schema should fall back to the default daily time when omitted."""
    options = _default_options()
    options.pop(CONF_DAILY_TIME)

    schema = _schedule_schema(options)
    validated = schema(
        {
            CONF_SCHEDULE_ENABLED: True,
            CONF_INTERVAL: 8,
            CONF_INTERVAL_UNIT: "hours",
        }
    )

    assert validated[CONF_DAILY_TIME] == DEFAULT_DAILY_TIME


@pytest.mark.asyncio
async def test_storage_step_shows_backup_root_note() -> None:
    """Selecting the backup root should surface a note placeholder for the user."""
    flow = _make_options_flow({**_default_options(), CONF_STORAGE_ROOT: "backup"})
    flow._options = {**_default_options(), CONF_STORAGE_ROOT: "backup"}

    result = await flow.async_step_storage()

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "storage"
    assert result["description_placeholders"] == {
        "backup_root_note": "/backup is Home Assistant's backup-storage mount."
    }


@pytest.mark.asyncio
async def test_schedule_step_uses_default_daily_time_when_blank() -> None:
    """A blank daily time should be replaced with the default schedule time."""
    flow = _make_options_flow()
    flow._options = _default_options()

    result = await flow.async_step_schedule(
        {
            CONF_SCHEDULE_ENABLED: True,
            CONF_INTERVAL: 12,
            CONF_INTERVAL_UNIT: "days",
            CONF_DAILY_TIME: "",
        }
    )

    assert flow._options[CONF_DAILY_TIME] == DEFAULT_DAILY_TIME
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "storage"


@pytest.mark.asyncio
async def test_contents_step_shows_form_without_input() -> None:
    """The contents step should render a form before any user input is supplied."""
    flow = _make_options_flow()
    flow._options = _default_options()

    result = await flow.async_step_contents()

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "contents"


@pytest.mark.asyncio
async def test_retention_step_rejects_negative_values() -> None:
    """Direct retention validation should reject negative values for both fields."""
    flow = _make_options_flow()
    flow._options = _default_options()

    result = await flow.async_step_retention(
        {
            CONF_RETENTION_COUNT: -1,
            CONF_RETENTION_DAYS: -5,
        }
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "retention"
    assert result["errors"] == {
        CONF_RETENTION_COUNT: "invalid_retention_count",
        CONF_RETENTION_DAYS: "invalid_retention_days",
    }


@pytest.mark.asyncio
async def test_behavior_step_shows_form_without_input() -> None:
    """The behavior step should render its form when first opened."""
    flow = _make_options_flow()
    flow._options = _default_options()

    result = await flow.async_step_behavior()

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "behavior"