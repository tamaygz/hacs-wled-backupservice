"""Tests for the retention policy implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from custom_components.wled_backupservice.manager import WLEDBackupManager
from custom_components.wled_backupservice.retention import async_prune_backups
from custom_components.wled_backupservice.storage import (
    StoredBackup,
    StoredBackupDevice,
    StoredBackupFile,
)


@dataclass
class FakeEntry:
    """Minimal config entry stand-in for manager prune tests."""

    options: dict[str, object]


class FakeStorage:
    """Storage stub exposing list/delete behavior for retention tests."""

    def __init__(
        self,
        backups: list[StoredBackup],
        *,
        failing_delete_ids: set[str] | None = None,
    ) -> None:
        self._backups = backups
        self.deleted_ids: list[str] = []
        self.failing_delete_ids = failing_delete_ids or set()

    async def async_list(self, device_id: str | None = None) -> list[StoredBackup]:
        if device_id is None:
            return list(self._backups)
        return [
            backup
            for backup in self._backups
            if backup.device.device_id == device_id
        ]

    async def async_delete(self, backup_id: str) -> None:
        if backup_id in self.failing_delete_ids:
            raise OSError("delete failed")
        self.deleted_ids.append(backup_id)


def _make_backup(
    *,
    backup_id: str,
    created_at: datetime,
    device_id: str = "device-one",
    device_name: str = "Kitchen",
) -> StoredBackup:
    """Create a stored backup descriptor for retention tests."""
    return StoredBackup(
        backup_id=backup_id,
        path=Path("C:/backups") / backup_id.replace("/", "\\"),
        created_at=created_at,
        integration_version="1.0.0",
        device=StoredBackupDevice(
            name=device_name,
            host="10.0.0.10",
            mac=device_id,
            device_id=device_id,
            firmware_version="0.16.0",
        ),
        files=(StoredBackupFile(name="cfg.json", size=2, sha256="hash"),),
    )


def _make_manager(
    options: dict[str, object],
    storage: FakeStorage,
) -> WLEDBackupManager:
    """Create a manager for prune delegation tests."""
    manager = WLEDBackupManager(hass=object(), entry=FakeEntry(options=options))
    manager.storage = storage
    return manager


@pytest.mark.asyncio
async def test_count_retention_keeps_newest_n() -> None:
    """Count-based retention should keep the newest N backups."""
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    backups = [
        _make_backup(
            backup_id=f"device-one/2026/09/27/12000{index}",
            created_at=now - timedelta(minutes=index),
        )
        for index in range(4)
    ]
    storage = FakeStorage(backups)

    result = await async_prune_backups(
        storage,
        retention_count=2,
        retention_days=0,
    )

    device_result = result.device_results[0]
    assert device_result.kept_backup_ids == (
        "device-one/2026/09/27/120000",
        "device-one/2026/09/27/120001",
    )
    assert device_result.deleted_backup_ids == (
        "device-one/2026/09/27/120002",
        "device-one/2026/09/27/120003",
    )
    assert storage.deleted_ids == list(device_result.deleted_backup_ids)


@pytest.mark.asyncio
async def test_age_retention_deletes_only_old_entries() -> None:
    """Age-based retention should prune only entries older than the threshold."""
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    backups = [
        _make_backup(backup_id="device-one/recent", created_at=now - timedelta(days=1)),
        _make_backup(backup_id="device-one/old", created_at=now - timedelta(days=10)),
    ]
    storage = FakeStorage(backups)

    result = await async_prune_backups(
        storage,
        retention_count=0,
        retention_days=5,
        now=now,
    )

    device_result = result.device_results[0]
    assert device_result.kept_backup_ids == ("device-one/recent",)
    assert device_result.deleted_backup_ids == ("device-one/old",)


@pytest.mark.asyncio
async def test_combined_retention_uses_union_of_count_and_age() -> None:
    """Combined retention should delete backups that violate either policy."""
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    backups = [
        _make_backup(backup_id="device-one/newest", created_at=now),
        _make_backup(backup_id="device-one/mid", created_at=now - timedelta(days=2)),
        _make_backup(backup_id="device-one/old", created_at=now - timedelta(days=20)),
    ]
    storage = FakeStorage(backups)

    result = await async_prune_backups(
        storage,
        retention_count=2,
        retention_days=10,
        now=now,
    )

    device_result = result.device_results[0]
    assert device_result.kept_backup_ids == (
        "device-one/newest",
        "device-one/mid",
    )
    assert device_result.deleted_backup_ids == ("device-one/old",)


@pytest.mark.asyncio
async def test_keep_all_when_both_policies_are_zero() -> None:
    """Zero count and zero age should keep every backup."""
    backups = [
        _make_backup(
            backup_id="device-one/backup",
            created_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        )
    ]
    storage = FakeStorage(backups)

    result = await async_prune_backups(
        storage,
        retention_count=0,
        retention_days=0,
    )

    device_result = result.device_results[0]
    assert device_result.kept_backup_ids == ("device-one/backup",)
    assert device_result.deleted_backup_ids == ()
    assert storage.deleted_ids == []


@pytest.mark.asyncio
async def test_dry_run_reports_without_deleting() -> None:
    """Dry-run should report would-delete ids but not perform deletions."""
    backups = [
        _make_backup(
            backup_id="device-one/a",
            created_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        ),
        _make_backup(
            backup_id="device-one/b",
            created_at=datetime(2026, 9, 27, 11, 0, tzinfo=UTC),
        ),
    ]
    storage = FakeStorage(backups)

    result = await async_prune_backups(
        storage,
        retention_count=1,
        retention_days=0,
        dry_run=True,
    )

    device_result = result.device_results[0]
    assert result.dry_run is True
    assert device_result.would_delete_backup_ids == ("device-one/b",)
    assert device_result.deleted_backup_ids == ()
    assert storage.deleted_ids == []


@pytest.mark.asyncio
async def test_delete_failure_does_not_abort_other_entries() -> None:
    """One deletion failure should not stop the rest of the prune run."""
    backups = [
        _make_backup(
            backup_id="device-one/a",
            created_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        ),
        _make_backup(
            backup_id="device-one/b",
            created_at=datetime(2026, 9, 27, 11, 0, tzinfo=UTC),
        ),
        _make_backup(
            backup_id="device-one/c",
            created_at=datetime(2026, 9, 27, 10, 0, tzinfo=UTC),
        ),
    ]
    storage = FakeStorage(backups, failing_delete_ids={"device-one/b"})

    result = await async_prune_backups(
        storage,
        retention_count=1,
        retention_days=0,
    )

    device_result = result.device_results[0]
    assert device_result.failed_backup_ids == ("device-one/b",)
    assert device_result.deleted_backup_ids == ("device-one/c",)
    assert storage.deleted_ids == ["device-one/c"]


@pytest.mark.asyncio
async def test_device_filter_and_naive_now_normalization() -> None:
    """A device filter should scope prune and naive times should normalize."""
    backups = [
        _make_backup(
            backup_id="device-one/a",
            created_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
            device_id="device-one",
        ),
        _make_backup(
            backup_id="device-two/a",
            created_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
            device_id="device-two",
            device_name="Bedroom",
        ),
    ]
    storage = FakeStorage(backups)

    result = await async_prune_backups(
        storage,
        retention_count=0,
        retention_days=5,
        device="device-two",
        now=datetime(2026, 9, 27, 12, 0),
    )

    assert len(result.device_results) == 1
    assert result.device_results[0].device_id == "device-two"
    assert result.device_results[0].deleted_backup_ids == ("device-two/a",)


@pytest.mark.asyncio
async def test_manager_async_prune_delegates_to_retention() -> None:
    """Manager prune should delegate with option-derived policy values."""
    backups = [
        _make_backup(
            backup_id="device-one/a",
            created_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        )
    ]
    storage = FakeStorage(backups)
    manager = _make_manager(
        {"retention_count": 3, "retention_days": 7},
        storage,
    )

    result = await manager.async_prune(device="device-one", dry_run=True)

    assert result.dry_run is True
    assert len(result.device_results) == 1
    assert result.device_results[0].device_id == "device-one"