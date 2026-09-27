"""Tests for translation assets and user-facing UI text."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from custom_components.wled_backupservice.const import INTERVAL_UNITS, STORAGE_ROOTS

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "wled_backupservice"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        values: list[str] = []
        for value in node.values():
            values.extend(_iter_strings(value))
        return values
    if isinstance(node, list):
        values = []
        for value in node:
            values.extend(_iter_strings(value))
        return values
    return []


def test_translation_assets_are_flat_and_in_sync() -> None:
    strings = _load_json(COMPONENT / "strings.json")
    en = _load_json(COMPONENT / "translations" / "en.json")

    assert strings == en
    assert all("[%key:" not in value for value in _iter_strings(en))


def test_translations_cover_config_options_and_selector_keys() -> None:
    en = _load_json(COMPONENT / "translations" / "en.json")
    config_flow_source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")

    abort_reasons = set(
        re.findall(r'async_abort\(reason="([^"]+)"', config_flow_source)
    )
    error_keys = set(re.findall(r'= "([a-z_]+)"', config_flow_source)) & {
        "invalid_interval",
        "invalid_subdir",
        "invalid_retention_count",
        "invalid_retention_days",
    }
    selector_keys = set(re.findall(r'translation_key=([A-Z_]+)', config_flow_source))

    assert abort_reasons <= set(en["config"]["abort"])
    assert error_keys <= set(en["options"]["error"])

    option_steps = {
        "schedule": {
            "schedule_enabled",
            "interval",
            "interval_unit",
            "daily_time",
        },
        "storage": {"storage_root", "subdir"},
        "contents": {"include_presets", "include_state", "create_archive"},
        "retention": {"retention_count", "retention_days"},
        "behavior": {
            "backup_before_restore",
            "verify_after_restore",
            "reboot_after_restore",
        },
    }

    for step, keys in option_steps.items():
        assert keys <= set(en["options"]["step"][step]["data"])
        assert keys <= set(en["options"]["step"][step]["data_description"])

    assert en["config"]["step"]["user"]["description"]
    assert "CONF_INTERVAL_UNIT" in selector_keys
    assert "CONF_STORAGE_ROOT" in selector_keys
    assert set(en["selector"]["interval_unit"]["options"]) == set(INTERVAL_UNITS)
    assert set(en["selector"]["storage_root"]["options"]) == set(STORAGE_ROOTS)


def test_service_translations_match_services_yaml_and_warn_for_restore() -> None:
    en = _load_json(COMPONENT / "translations" / "en.json")
    services_yaml = yaml.safe_load(
        (COMPONENT / "services.yaml").read_text(encoding="utf-8")
    )

    assert set(services_yaml) <= set(en["services"])

    for service_name, definition in services_yaml.items():
        translation = en["services"][service_name]
        assert translation["name"]
        assert translation["description"]
        fields = definition.get("fields", {})
        if fields:
            assert "fields" in translation
            assert set(fields) <= set(translation["fields"])

    restore_description = en["services"]["restore"]["description"].lower()
    assert "destructive" in restore_description
    assert "connectivity" in restore_description or "connect" in restore_description
    assert "reboot" in restore_description


def test_exception_translations_cover_translated_runtime_errors() -> None:
    en = _load_json(COMPONENT / "translations" / "en.json")

    expected_keys = {
        "config_entry_not_loaded",
        "config_entry_not_ready",
        "target_required",
        "restore_requires_single_device",
        "restore_not_available",
        "invalid_device_target",
        "unresolved_device_target",
    }

    assert expected_keys <= set(en["exceptions"])