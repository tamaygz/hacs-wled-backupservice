"""Structured result models for the WLED Backup Service integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class BackupResult:
    """Structured result for a single backup attempt."""

    device_id: str
    device_name: str
    success: bool
    backup_id: str | None
    path: Path | None
    files: tuple[str, ...]
    created_at: datetime | None
    error: str | None = None