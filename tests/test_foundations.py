"""Validation tests for manifest and shared integration foundations."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.exceptions import HomeAssistantError

from custom_components.wled_backupservice import const, exceptions
from custom_components.wled_backupservice.manager import INTEGRATION_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_has_required_hacs_fields() -> None:
    """The integration manifest should include the HACS-required keys."""
    manifest = json.loads(
        (ROOT / "custom_components" / "wled_backupservice" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["domain"] == const.DOMAIN
    assert manifest["name"] == const.NAME
    assert manifest["codeowners"] == ["@tamaygz"]
    assert manifest["documentation"]
    assert manifest["issue_tracker"]
    assert manifest["version"] == INTEGRATION_VERSION
    assert manifest["single_config_entry"] is True


def test_hacs_json_has_required_keys() -> None:
    """The HACS metadata file should contain the required fields."""
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))

    assert hacs["name"] == const.NAME
    assert hacs["homeassistant"] == "2025.12.0"


def test_brand_icon_exists() -> None:
    """The repository should include the HACS-required brand icon file."""
    assert (
        ROOT / "custom_components" / "wled_backupservice" / "brand" / "icon.png"
    ).exists()


def test_custom_exceptions_subclass_homeassistant_error() -> None:
    """All public custom exceptions should subclass HomeAssistantError."""
    public_exceptions = (
        exceptions.WLEDBackupError,
        exceptions.WLEDConnectionError,
        exceptions.WLEDValidationError,
        exceptions.WLEDBackupNotFoundError,
        exceptions.WLEDRestoreError,
        exceptions.WLEDStorageError,
        exceptions.WLEDDiscoveryError,
    )

    assert all(issubclass(exc, HomeAssistantError) for exc in public_exceptions)