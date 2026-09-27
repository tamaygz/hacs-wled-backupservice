"""Tests for the backup storage service."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from custom_components.wled_backupservice.exceptions import (
    WLEDBackupNotFoundError,
    WLEDStorageError,
    WLEDValidationError,
)
from custom_components.wled_backupservice.storage import BackupStorage


class FakeHass:
    """Minimal Home Assistant stub for executor-backed storage tests."""

    def __init__(self, config_root: Path) -> None:
        self._executor_calls = 0
        self.config = SimpleNamespace(path=lambda *_parts: str(config_root))

    @property
    def executor_calls(self) -> int:
        """Return the number of executor invocations made so far."""
        return self._executor_calls

    async def async_add_executor_job(self, func, *args):
        """Run a blocking function synchronously while recording the offload call."""
        self._executor_calls += 1
        return func(*args)


def _make_storage(
    tmp_path: Path,
    *,
    storage_root: str = "config",
    subdir: str = "wled_backups",
) -> BackupStorage:
    """Build a storage service rooted in a temporary config directory."""
    config_root = tmp_path / "config-root"
    config_root.mkdir(parents=True, exist_ok=True)
    return BackupStorage(
        FakeHass(config_root),
        storage_root=storage_root,
        subdir=subdir,
        integration_version="1.0.0",
    )


def test_write_backup_creates_expected_layout_and_manifest(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Writing a backup should create a dated directory with a verifiable manifest."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)
    created_at = datetime(2026, 9, 27, 2, 43, 0, tzinfo=UTC)

    backup = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen Strip",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version="0.16.0",
            files={
                "cfg.json": b'{"wifi": {}}',
                "presets.json": b'{"1": {"n": "Preset 1"}}',
            },
            created_at=created_at,
        )
    )

    assert backup.backup_id == "Kitchen_Strip_aabbccddeeff/2026/09/27/024300"
    assert backup.path.is_dir()
    assert (backup.path / "manifest.json").exists()
    assert storage.hass.executor_calls >= 1

    reloaded = asyncio.run(storage.async_read_backup(backup.backup_id))
    assert reloaded.device.device_id == "aabbccddeeff"
    assert {item.name for item in reloaded.files} == {"cfg.json", "presets.json"}


def test_storage_rejects_subdir_traversal(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Subdirectory traversal should be rejected at the storage boundary."""
    _ = socket_enabled
    storage = _make_storage(tmp_path, subdir="../escape")

    with pytest.raises(WLEDValidationError, match="invalid_subdir"):
        asyncio.run(
            storage.async_write_backup(
                device_name="Kitchen",
                host="10.0.0.10",
                device_id="aabbccddeeff",
                mac="aabbccddeeff",
                firmware_version=None,
                files={"cfg.json": b"{}"},
            )
        )


def test_atomic_commit_cleans_staging_on_failure(
    tmp_path: Path,
    socket_enabled: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure before manifest commit should not leave a final or staging directory."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)

    def fail_manifest(_staging_dir: Path, _manifest: dict[str, object]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(storage, "_write_manifest_sync", fail_manifest)

    with pytest.raises(OSError, match="disk full"):
        asyncio.run(
            storage.async_write_backup(
                device_name="Kitchen",
                host="10.0.0.10",
                device_id="aabbccddeeff",
                mac="aabbccddeeff",
                firmware_version=None,
                files={"cfg.json": b"{}"},
                created_at=datetime(2026, 9, 27, 2, 43, 0, tzinfo=UTC),
            )
        )

    backup_root = tmp_path / "config-root" / "wled_backups"
    assert list(backup_root.rglob("manifest.json")) == []
    assert not any(path.name.startswith(".024300-") for path in backup_root.rglob("*"))


def test_read_backup_detects_hash_mismatch(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Tampering with a stored file should fail SHA-256 verification."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)

    backup = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 0, tzinfo=UTC),
        )
    )
    (backup.path / "cfg.json").write_bytes(b"[]")

    with pytest.raises(WLEDStorageError, match="failed SHA-256 verification"):
        asyncio.run(storage.async_read_backup(backup.backup_id))


def test_name_collision_produces_unique_device_dirs(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Two devices with the same display name should still get unique directories."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)

    first = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 0, tzinfo=UTC),
        )
    )
    second = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.11",
            device_id="112233445566",
            mac="112233445566",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 1, tzinfo=UTC),
        )
    )

    assert first.backup_id.split("/")[0] != second.backup_id.split("/")[0]


def test_async_list_skips_unknown_dirs_and_sorts_newest_first(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Listing should return only validated backups sorted newest-first."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)

    first = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 0, tzinfo=UTC),
        )
    )
    second = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 44, 0, tzinfo=UTC),
        )
    )
    unknown_dir = tmp_path / "config-root" / "wled_backups" / "unknown" / "2026" / "09" / "27" / "999999"
    unknown_dir.mkdir(parents=True)

    backups = asyncio.run(storage.async_list())
    assert [item.backup_id for item in backups] == [second.backup_id, first.backup_id]


def test_delete_refuses_unknown_dirs_and_deletes_valid_backup(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Delete should remove validated backups and reject unknown directories."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)
    backup = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 0, tzinfo=UTC),
        )
    )

    asyncio.run(storage.async_delete(backup.backup_id))
    with pytest.raises(WLEDBackupNotFoundError):
        asyncio.run(storage.async_read_backup(backup.backup_id))

    unknown_dir = tmp_path / "config-root" / "wled_backups" / "odd" / "2026" / "09" / "27" / "020000"
    unknown_dir.mkdir(parents=True)
    with pytest.raises(WLEDStorageError, match="missing manifest.json"):
        asyncio.run(storage.async_delete("odd/2026/09/27/020000"))


def test_resolve_backup_id_revalidates_containment(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Backup ids should be relative and stay confined to the resolved root."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)

    with pytest.raises(WLEDValidationError, match="relative paths"):
        asyncio.run(storage.async_resolve_backup_id("../escape"))


def test_storage_root_must_exist(
    tmp_path: Path,
    socket_enabled: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-config roots should fail clearly when the resolved root does not exist."""
    _ = socket_enabled
    storage = _make_storage(tmp_path, storage_root="share")
    missing_root = str(tmp_path / "missing-share")
    monkeypatch.setitem(__import__("custom_components.wled_backupservice.storage", fromlist=["STORAGE_ROOTS"]).STORAGE_ROOTS, "share", missing_root)

    with pytest.raises(WLEDStorageError, match="does not exist"):
        asyncio.run(
            storage.async_write_backup(
                device_name="Kitchen",
                host="10.0.0.10",
                device_id="aabbccddeeff",
                mac="aabbccddeeff",
                firmware_version=None,
                files={"cfg.json": b"{}"},
            )
        )


def test_write_backup_requires_at_least_one_file(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Writing an empty backup should fail validation."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)

    with pytest.raises(WLEDValidationError, match="At least one backup file"):
        asyncio.run(
            storage.async_write_backup(
                device_name="Kitchen",
                host="10.0.0.10",
                device_id="aabbccddeeff",
                mac="aabbccddeeff",
                firmware_version=None,
                files={},
            )
        )


def test_resolve_backup_id_rejects_drive_prefix_and_missing_backups(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Backup ids should reject drive prefixes and missing directories."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)

    with pytest.raises(WLEDValidationError, match="drive prefixes"):
        asyncio.run(storage.async_resolve_backup_id("C:/bad/path"))

    with pytest.raises(WLEDBackupNotFoundError, match="was not found"):
        asyncio.run(storage.async_resolve_backup_id("Kitchen/2026/09/27/024300"))


def test_async_list_returns_empty_when_backup_root_missing(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Listing should return an empty list before any backup subdir exists."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)

    assert asyncio.run(storage.async_list()) == []


def test_async_list_filters_by_device_id_and_skips_invalid_manifests(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Listing should filter by device id and skip malformed backup directories."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)

    keep = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="keepme",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 0, tzinfo=UTC),
        )
    )
    asyncio.run(
        storage.async_write_backup(
            device_name="Bedroom",
            host="10.0.0.11",
            device_id="skipme",
            mac="112233445566",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 44, 0, tzinfo=UTC),
        )
    )
    broken_manifest = tmp_path / "config-root" / "wled_backups" / "broken" / "2026" / "09" / "27" / "000000"
    broken_manifest.mkdir(parents=True)
    (broken_manifest / "manifest.json").write_text("{}", encoding="utf-8")

    backups = asyncio.run(storage.async_list(device_id="keepme"))

    assert [item.backup_id for item in backups] == [keep.backup_id]


def test_read_backup_detects_size_mismatch_and_missing_metadata(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Read verification should catch size changes and missing device metadata."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)
    backup = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 0, tzinfo=UTC),
        )
    )

    (backup.path / "cfg.json").write_bytes(b'{"tampered": true}')
    with pytest.raises(WLEDStorageError, match="size mismatch"):
        asyncio.run(storage.async_read_backup(backup.backup_id))

    backup = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="bbccddeeff00",
            mac="bbccddeeff00",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 1, tzinfo=UTC),
        )
    )
    manifest_path = backup.path / "manifest.json"
    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("device")
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")

    with pytest.raises(WLEDStorageError, match="missing device metadata"):
        asyncio.run(storage.async_read_backup(backup.backup_id))


def test_read_backup_detects_schema_created_at_and_missing_file_errors(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Manifest schema, timestamps, and referenced files should all be verified."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)
    backup = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 0, tzinfo=UTC),
        )
    )
    manifest_path = backup.path / "manifest.json"
    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 999
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")

    with pytest.raises(WLEDStorageError, match="unsupported schema"):
        asyncio.run(storage.async_read_backup(backup.backup_id))

    backup = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 2, tzinfo=UTC),
        )
    )
    manifest_path = backup.path / "manifest.json"
    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_at"] = "not-a-date"
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")

    with pytest.raises(WLEDStorageError, match="invalid created_at"):
        asyncio.run(storage.async_read_backup(backup.backup_id))

    backup = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=datetime(2026, 9, 27, 2, 43, 3, tzinfo=UTC),
        )
    )
    (backup.path / "cfg.json").unlink()

    with pytest.raises(WLEDStorageError, match="missing file"):
        asyncio.run(storage.async_read_backup(backup.backup_id))


def test_write_backup_rejects_invalid_file_names_and_unknown_storage_root(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Bad file names and unsupported storage roots should fail fast."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)
    with pytest.raises(WLEDValidationError, match="Invalid backup file name"):
        asyncio.run(
            storage.async_write_backup(
                device_name="Kitchen",
                host="10.0.0.10",
                device_id="aabbccddeeff",
                mac="aabbccddeeff",
                firmware_version=None,
                files={"../cfg.json": b"{}"},
            )
        )

    storage = _make_storage(tmp_path, storage_root="invalid-root")
    with pytest.raises(WLEDValidationError, match="Unsupported storage root"):
        asyncio.run(
            storage.async_list()
        )


def test_write_backup_detects_existing_final_directory_and_normalizes_naive_datetime(
    tmp_path: Path,
    socket_enabled: None,
) -> None:
    """Existing final directories should fail and naive datetimes should be normalized."""
    _ = socket_enabled
    storage = _make_storage(tmp_path)
    created_at = datetime(2026, 9, 27, 2, 43, 0)
    final_dir = (
        tmp_path
        / "config-root"
        / "wled_backups"
        / "Kitchen_aabbccddeeff"
        / "2026"
        / "09"
        / "27"
        / "024300"
    )
    final_dir.mkdir(parents=True)

    with pytest.raises(WLEDStorageError, match="already exists"):
        asyncio.run(
            storage.async_write_backup(
                device_name="Kitchen",
                host="10.0.0.10",
                device_id="aabbccddeeff",
                mac="aabbccddeeff",
                firmware_version=None,
                files={"cfg.json": b"{}"},
                created_at=created_at,
            )
        )

    shutil.rmtree(final_dir)
    backup = asyncio.run(
        storage.async_write_backup(
            device_name="Kitchen",
            host="10.0.0.10",
            device_id="aabbccddeeff",
            mac="aabbccddeeff",
            firmware_version=None,
            files={"cfg.json": b"{}"},
            created_at=created_at,
        )
    )
    assert backup.created_at.tzinfo is UTC