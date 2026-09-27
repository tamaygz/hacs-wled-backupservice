"""Filesystem storage service for WLED backups."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import BACKUP_SCHEMA_VERSION, MANIFEST_FILENAME, STORAGE_ROOTS
from .exceptions import (
    WLEDBackupNotFoundError,
    WLEDStorageError,
    WLEDValidationError,
)
from .validators import normalize_backup_subdir

HASH_CHUNK_SIZE = 64 * 1024
DEVICE_SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True)
class StoredBackupFile:
    """Manifest entry for a stored backup file."""

    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class StoredBackupDevice:
    """Device metadata recorded in a backup manifest."""

    name: str
    host: str
    mac: str | None
    device_id: str
    firmware_version: str | None


@dataclass(frozen=True)
class StoredBackup:
    """Validated descriptor for a stored backup directory."""

    backup_id: str
    path: Path
    created_at: datetime
    integration_version: str
    device: StoredBackupDevice
    files: tuple[StoredBackupFile, ...]


class BackupStorage:
    """Filesystem abstraction for atomic WLED backups."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        storage_root: str,
        subdir: str,
        integration_version: str = "unknown",
    ) -> None:
        """Initialize the storage service."""
        self.hass = hass
        self.storage_root = storage_root
        self.subdir = subdir
        self.integration_version = integration_version

    async def async_write_backup(
        self,
        *,
        device_name: str,
        host: str,
        device_id: str,
        mac: str | None,
        firmware_version: str | None,
        files: Mapping[str, bytes],
        created_at: datetime | None = None,
    ) -> StoredBackup:
        """Atomically persist a backup and return its validated descriptor."""
        created = created_at or dt_util.utcnow()
        return await self.hass.async_add_executor_job(
            self._write_backup_sync,
            device_name,
            host,
            device_id,
            mac,
            firmware_version,
            dict(files),
            created,
        )

    async def async_read_backup(self, backup_id: str) -> StoredBackup:
        """Read and verify a backup by its opaque id."""
        return await self.hass.async_add_executor_job(
            self._read_backup_sync,
            backup_id,
        )

    async def async_read_backup_file(self, backup_id: str, file_name: str) -> bytes:
        """Read a validated backup file by name."""
        return await self.hass.async_add_executor_job(
            self._read_backup_file_sync,
            backup_id,
            file_name,
        )

    async def async_list(self, device_id: str | None = None) -> list[StoredBackup]:
        """List valid backups under the configured root."""
        return await self.hass.async_add_executor_job(
            self._list_backups_sync, device_id
        )

    async def async_delete(self, backup_id: str) -> None:
        """Delete a validated backup directory."""
        await self.hass.async_add_executor_job(self._delete_backup_sync, backup_id)

    async def async_resolve_backup_id(self, backup_id: str) -> Path:
        """Resolve a backup id to its absolute directory path."""
        return await self.hass.async_add_executor_job(
            self._resolve_backup_id_sync,
            backup_id,
        )

    def _write_backup_sync(
        self,
        device_name: str,
        host: str,
        device_id: str,
        mac: str | None,
        firmware_version: str | None,
        files: dict[str, bytes],
        created_at: datetime,
    ) -> StoredBackup:
        if not files:
            raise WLEDValidationError("At least one backup file is required")

        storage_root = self._resolved_storage_root()
        backup_root = self._resolved_backup_root(storage_root)
        device_dir = self._device_dir_name(device_name, device_id)
        created = self._normalize_datetime(created_at)

        final_parent = (
            backup_root
            / device_dir
            / created.strftime("%Y")
            / created.strftime("%m")
            / created.strftime("%d")
        )
        final_name = created.strftime("%H%M%S")
        final_dir = self._assert_within_root(final_parent / final_name, backup_root)

        final_parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(tempfile.mkdtemp(prefix=f".{final_name}-", dir=final_parent))

        try:
            manifest_files: list[StoredBackupFile] = []
            for file_name, payload in files.items():
                file_path = staging_dir / self._validate_file_name(file_name)
                file_path.write_bytes(payload)
                manifest_files.append(
                    StoredBackupFile(
                        name=file_path.name,
                        size=file_path.stat().st_size,
                        sha256=self._hash_file(file_path),
                    )
                )

            manifest = {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "created_at": created.isoformat(),
                "integration_version": self.integration_version,
                "device": asdict(
                    StoredBackupDevice(
                        name=device_name,
                        host=host,
                        mac=mac,
                        device_id=device_id,
                        firmware_version=firmware_version,
                    )
                ),
                "files": [asdict(file_record) for file_record in manifest_files],
            }
            self._write_manifest_sync(staging_dir, manifest)

            if final_dir.exists():
                raise WLEDStorageError(f"Backup directory already exists: {final_dir}")
            os.replace(staging_dir, final_dir)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

        backup_id = final_dir.relative_to(backup_root).as_posix()
        return self._read_backup_from_path_sync(final_dir, backup_id, backup_root)

    def _read_backup_sync(self, backup_id: str) -> StoredBackup:
        backup_root = self._resolved_backup_root(self._resolved_storage_root())
        backup_dir = self._resolve_backup_id_sync(backup_id)
        return self._read_backup_from_path_sync(backup_dir, backup_id, backup_root)

    def _read_backup_file_sync(self, backup_id: str, file_name: str) -> bytes:
        backup_root = self._resolved_backup_root(self._resolved_storage_root())
        backup_dir = self._resolve_backup_id_sync(backup_id)
        descriptor = self._read_backup_from_path_sync(
            backup_dir,
            backup_id,
            backup_root,
        )
        normalized_name = self._validate_file_name(file_name)
        if normalized_name not in {
            stored_file.name for stored_file in descriptor.files
        }:
            raise WLEDStorageError(
                f"Backup {backup_id!r} does not contain file {normalized_name!r}"
            )
        file_path = self._assert_within_root(backup_dir / normalized_name, backup_root)
        return file_path.read_bytes()

    def _list_backups_sync(self, device_id: str | None) -> list[StoredBackup]:
        backup_root = self._resolved_backup_root(self._resolved_storage_root())
        if not backup_root.exists():
            return []

        backups: list[StoredBackup] = []
        for manifest_path in backup_root.rglob(MANIFEST_FILENAME):
            try:
                backup_dir = self._assert_within_root(manifest_path.parent, backup_root)
                backup_id = backup_dir.relative_to(backup_root).as_posix()
                descriptor = self._read_backup_from_path_sync(
                    backup_dir,
                    backup_id,
                    backup_root,
                )
            except (WLEDStorageError, WLEDValidationError, WLEDBackupNotFoundError):
                continue

            if device_id is None or descriptor.device.device_id == device_id:
                backups.append(descriptor)

        backups.sort(key=lambda backup: backup.created_at, reverse=True)
        return backups

    def _delete_backup_sync(self, backup_id: str) -> None:
        backup_root = self._resolved_backup_root(self._resolved_storage_root())
        backup_dir = self._resolve_backup_id_sync(backup_id)
        self._read_backup_from_path_sync(backup_dir, backup_id, backup_root)
        shutil.rmtree(backup_dir)

    def _resolve_backup_id_sync(self, backup_id: str) -> Path:
        backup_root = self._resolved_backup_root(self._resolved_storage_root())
        relative_id = backup_id.replace("\\", "/")
        if PureWindowsPath(relative_id).drive:
            raise WLEDValidationError("Backup ids must not contain drive prefixes")

        relative_path = PurePosixPath(relative_id)
        if relative_path.is_absolute() or any(
            part in ("", ".", "..") for part in relative_path.parts
        ):
            raise WLEDValidationError(
                "Backup ids must be relative paths inside the storage root"
            )

        resolved = self._assert_within_root(
            backup_root.joinpath(*relative_path.parts), backup_root
        )
        if not resolved.exists() or not resolved.is_dir():
            raise WLEDBackupNotFoundError(f"Backup {backup_id!r} was not found")
        return resolved

    def _read_backup_from_path_sync(
        self,
        backup_dir: Path,
        backup_id: str,
        backup_root: Path,
    ) -> StoredBackup:
        backup_dir = self._assert_within_root(backup_dir, backup_root)
        manifest_path = backup_dir / MANIFEST_FILENAME
        if not manifest_path.exists():
            raise WLEDStorageError(
                f"Backup {backup_id!r} is missing {MANIFEST_FILENAME}"
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
            schema_version = manifest.get("schema_version")
            raise WLEDStorageError(
                f"Backup {backup_id!r} uses unsupported schema {schema_version!r}"
            )

        created_at_raw = manifest.get("created_at")
        created_at = dt_util.parse_datetime(created_at_raw)
        if created_at is None:
            raise WLEDStorageError(f"Backup {backup_id!r} has an invalid created_at")

        files_data = manifest.get("files")
        if not isinstance(files_data, list) or not files_data:
            raise WLEDStorageError(f"Backup {backup_id!r} does not list any files")

        files: list[StoredBackupFile] = []
        for file_info in files_data:
            file_record = StoredBackupFile(
                name=str(file_info["name"]),
                size=int(file_info["size"]),
                sha256=str(file_info["sha256"]),
            )
            file_path = self._assert_within_root(
                backup_dir / file_record.name, backup_root
            )
            if not file_path.exists():
                raise WLEDStorageError(
                    f"Backup {backup_id!r} is missing file {file_record.name!r}"
                )

            actual_size = file_path.stat().st_size
            if actual_size != file_record.size:
                raise WLEDStorageError(
                    f"Backup {backup_id!r} file {file_record.name!r} size mismatch"
                )

            actual_hash = self._hash_file(file_path)
            if actual_hash != file_record.sha256:
                raise WLEDStorageError(
                    f"Backup {backup_id!r} file {file_record.name!r} "
                    "failed SHA-256 verification"
                )
            files.append(file_record)

        device_info = manifest.get("device")
        if not isinstance(device_info, dict):
            raise WLEDStorageError(f"Backup {backup_id!r} is missing device metadata")

        return StoredBackup(
            backup_id=backup_id,
            path=backup_dir,
            created_at=created_at,
            integration_version=str(manifest.get("integration_version", "unknown")),
            device=StoredBackupDevice(
                name=str(device_info["name"]),
                host=str(device_info["host"]),
                mac=device_info.get("mac"),
                device_id=str(device_info["device_id"]),
                firmware_version=device_info.get("firmware_version"),
            ),
            files=tuple(files),
        )

    def _write_manifest_sync(self, staging_dir: Path, manifest: dict[str, Any]) -> None:
        manifest_path = staging_dir / MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _resolved_storage_root(self) -> Path:
        if self.storage_root == "config":
            root = Path(self.hass.config.path())
        else:
            try:
                root = Path(STORAGE_ROOTS[self.storage_root])
            except KeyError as err:
                raise WLEDValidationError(
                    f"Unsupported storage root {self.storage_root!r}"
                ) from err

        resolved = root.resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise WLEDStorageError(
                f"Storage root {resolved} does not exist or is not writable"
            )
        return resolved

    def _resolved_backup_root(self, storage_root: Path) -> Path:
        try:
            normalized_subdir = normalize_backup_subdir(self.subdir)
        except vol.Invalid as err:
            raise WLEDValidationError(str(err)) from err
        backup_root = self._assert_within_root(
            storage_root / normalized_subdir, storage_root
        )
        return backup_root

    def _assert_within_root(self, path: Path, root: Path) -> Path:
        resolved_root = root.resolve()
        resolved_path = path.resolve(strict=False)
        if not resolved_path.is_relative_to(resolved_root):
            raise WLEDValidationError(
                f"Path {resolved_path} escapes storage root {resolved_root}"
            )
        return resolved_path

    def _validate_file_name(self, file_name: str) -> str:
        relative = PurePosixPath(file_name.replace("\\", "/"))
        if relative.is_absolute() or any(
            part in ("", ".", "..") for part in relative.parts
        ):
            raise WLEDValidationError(f"Invalid backup file name {file_name!r}")
        return relative.name

    def _device_dir_name(self, device_name: str, device_id: str) -> str:
        sanitized_name = (
            DEVICE_SEGMENT_PATTERN.sub("_", device_name).strip("_") or "device"
        )
        suffix = DEVICE_SEGMENT_PATTERN.sub("_", device_id).strip("_") or "id"
        return f"{sanitized_name}_{suffix}"

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            while chunk := file_handle.read(HASH_CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()

    def _normalize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
