"""Retention and pruning logic for stored WLED backups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .storage import StoredBackup


@dataclass(frozen=True)
class DevicePruneResult:
    """Prune outcome for a single device."""

    device_id: str
    total_backups: int
    kept_backup_ids: tuple[str, ...]
    would_delete_backup_ids: tuple[str, ...]
    deleted_backup_ids: tuple[str, ...]
    failed_backup_ids: tuple[str, ...]


@dataclass(frozen=True)
class PruneResult:
    """Structured prune result across one or more devices."""

    dry_run: bool
    device_results: tuple[DevicePruneResult, ...]


async def async_prune_backups(
    storage: Any,
    *,
    retention_count: int,
    retention_days: int,
    device: str | Any | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> PruneResult:
    """Apply retention policy to known valid backups."""
    normalized_device_id = _normalize_device_id(device)
    backups = await storage.async_list(normalized_device_id)
    if not backups:
        return PruneResult(dry_run=dry_run, device_results=())

    grouped: dict[str, list[StoredBackup]] = {}
    for backup in backups:
        grouped.setdefault(backup.device.device_id, []).append(backup)

    current_time = _normalize_now(now)
    cutoff = (
        current_time - timedelta(days=retention_days)
        if retention_days > 0
        else None
    )

    device_results: list[DevicePruneResult] = []
    for device_id, device_backups in grouped.items():
        sorted_backups = sorted(
            device_backups,
            key=lambda backup: backup.created_at,
            reverse=True,
        )

        delete_ids: set[str] = set()
        if retention_count > 0:
            delete_ids.update(
                backup.backup_id for backup in sorted_backups[retention_count:]
            )
        if cutoff is not None:
            delete_ids.update(
                backup.backup_id
                for backup in sorted_backups
                if backup.created_at < cutoff
            )

        would_delete = tuple(
            backup.backup_id
            for backup in sorted_backups
            if backup.backup_id in delete_ids
        )
        kept = tuple(
            backup.backup_id
            for backup in sorted_backups
            if backup.backup_id not in delete_ids
        )

        deleted: list[str] = []
        failed: list[str] = []
        if not dry_run:
            for backup_id in would_delete:
                try:
                    await storage.async_delete(backup_id)
                except Exception:
                    failed.append(backup_id)
                else:
                    deleted.append(backup_id)

        device_results.append(
            DevicePruneResult(
                device_id=device_id,
                total_backups=len(sorted_backups),
                kept_backup_ids=kept,
                would_delete_backup_ids=would_delete,
                deleted_backup_ids=tuple(deleted),
                failed_backup_ids=tuple(failed),
            )
        )

    return PruneResult(dry_run=dry_run, device_results=tuple(device_results))


def _normalize_device_id(device: str | Any | None) -> str | None:
    """Normalize a device or device id input to a string identifier."""
    if device is None:
        return None
    if isinstance(device, str):
        return device
    device_id = getattr(device, "device_id", None)
    return str(device_id) if device_id is not None else None


def _normalize_now(now: datetime | None) -> datetime:
    """Return a timezone-aware timestamp for retention comparisons."""
    reference = now or dt_util.utcnow()
    if reference.tzinfo is None:
        return reference.replace(tzinfo=dt_util.UTC)
    return reference.astimezone(dt_util.UTC)