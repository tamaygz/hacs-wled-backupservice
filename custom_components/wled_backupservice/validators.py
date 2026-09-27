"""Validation helpers for the WLED Backup Service integration."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

import voluptuous as vol

from .const import DEFAULT_SUBDIR


def normalize_backup_subdir(value: str) -> str:
    """Normalize a user-provided backup subdirectory.

    The returned path is always relative and uses POSIX separators so it can be
    safely combined with the storage root selected elsewhere in the integration.
    """
    stripped = value.strip()
    if not stripped:
        return DEFAULT_SUBDIR

    if PureWindowsPath(stripped).drive:
        raise vol.Invalid("invalid_subdir")

    normalized = stripped.replace("\\", "/")
    normalized_path = PurePosixPath(normalized)
    if normalized_path.is_absolute() or any(
        part == ".." for part in normalized_path.parts
    ):
        raise vol.Invalid("invalid_subdir")

    cleaned_parts = [part for part in normalized_path.parts if part not in ("", ".")]
    if not cleaned_parts:
        return DEFAULT_SUBDIR

    return PurePosixPath(*cleaned_parts).as_posix()