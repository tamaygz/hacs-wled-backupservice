---
goal: Implement the filesystem storage abstraction with path validation, atomic writes, and manifest/hash integrity
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [storage, filesystem, integrity, security]
---

# 07 — Storage service

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Provide `BackupStorage` that writes/reads/lists/deletes backups under an approved root,
using atomic staging→rename, a machine-readable `manifest.json` with SHA-256 hashes, and
strict path validation — all without blocking the event loop.

## Scope

In scope: `storage.py`, path resolver/validator, backup id scheme, manifest read/write,
integrity verification, list/delete primitives. Out of scope: which artifacts to fetch (08),
retention policy math (09), restore (11).

## Prerequisites / dependencies

- Plan **02** complete (const, exceptions). Independent of client/discovery.

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/storage.py
```

## Detailed implementation tasks

1. **Root resolution**: map `storage_root` option (`share/media/backup/config`) to an
   absolute base. Resolve `config` via `hass.config.path()`; the others map to
   `/share`, `/media`, `/backup`. Combine with the validated relative `subdir`. Reject any
   result that escapes the approved root.
2. **Path validation helper** (shared with config flow, plan 04):
   - `subdir` and device-dir segments must be relative, no `..`, no absolute/drive prefixes.
   - After joining, `Path.resolve()` and assert the result is within the resolved root
     (`is_relative_to`). Raise `WLEDStorageError`/`WLEDValidationError` otherwise.
   - Sanitize device directory names: allow `[A-Za-z0-9_-]`, replace others with `_`, and
     append a MAC-derived suffix to guarantee uniqueness (PRD §5).
3. **Layout** (PRD §5): `<root>/<subdir>/<Device_dir>/<YYYY>/<MM>/<DD>/<HHMMSS>/` containing
   `manifest.json`, `cfg.json`, `presets.json` (+ optional `state.json`/`info.json`,
   optional archive).
4. **Backup id scheme**: define a stable, opaque, URL-safe **backup id** that encodes
   device dir + timestamp path (e.g. `"<device_dir>/2026/09/27/024300"`), used by services
   (list/restore/delete) so callers never pass raw absolute paths. Provide
   `resolve_backup_id(id) -> Path` that re-validates containment inside the root.
5. **Atomic write** (`async_write_backup`): write all files into a **staging temp dir**
   inside the same root (same filesystem for atomic rename), compute SHA-256 for each file,
   write `manifest.json` last, then `os.replace`/`Path.rename` staging → final timestamp
   dir. On any failure, remove staging. Never expose a half-written dir as valid.
6. **Manifest** (PRD §4/§15): `schema_version`, `created_at` (tz-aware ISO), integration
   version, device block (name/host/mac/device_id/firmware), and `files[]` with
   `name/size/sha256`.
7. **Read/verify** (`async_read_backup`): parse manifest, check `schema_version` supported,
   verify each file's size + SHA-256, confirm required artifacts exist → return a validated
   backup descriptor (used by restore + list + retention).
8. **List/delete** (`async_list`, `async_delete`): enumerate valid backup dirs (optionally
   per device); delete only dirs whose manifest confidently identifies them as this
   integration's backups. Refuse to delete outside the resolved root.
9. **Async offloading**: all blocking filesystem ops run via `hass.async_add_executor_job`
   (glob, read, write, rename, hash). Do not call blocking I/O directly on the loop.

## API / framework requirements

- `hass.config.path()` for the config root; `hass.async_add_executor_job` for blocking I/O.
- `pathlib.Path`, `hashlib.sha256`, `os.replace` for atomic rename.
- `homeassistant.util.dt` for tz-aware timestamps.

## Important technical decisions

- Filesystem is the source of truth; **no database** in v1 (PRD §29). Manifest carries
  metadata.
- Staging dir must be on the **same filesystem/root** so rename is atomic.
- Backup ids are integration-generated and always re-resolved against the root — service
  callers can never supply arbitrary paths (PRD §11, §23).
- Unknown/unrecognized directories are **left untouched** (never deleted).

## Edge cases (PRD §22 storage suite)

- Correct directory structure; sanitization of odd names; path traversal rejection
  (`..`, absolute, drive letter); atomic commit (simulate crash mid-write → no valid dir);
  manifest creation; hash calculation; corrupted backup detection (tampered file → hash
  mismatch); deletion; two devices with same display name (unique dirs).
- Root does not exist / not writable → clear `WLEDStorageError` (do not create outside
  approved roots without permission; `/share` etc. are expected to exist on HAOS).
- Very large presets file hashing (chunked read).

## Security / safety considerations

- Enforce root containment on **every** path operation (write, read, list, delete, resolve).
- Never follow symlinks out of the root; resolve and re-check containment.
- Treat backup files as sensitive (may contain network/service config); do not log contents.

## Testing requirements

- Traversal rejection for `..`, absolute, and drive-letter inputs.
- Atomic commit: inject a failure before manifest write → assert no final dir remains.
- Hash mismatch detection on tampered file.
- Sanitization + uniqueness for name collisions.
- List/delete confined to root; refuse unknown dirs.
- All I/O offloaded (assert no blocking-call warnings under HA test harness).

## Acceptance criteria

- [x] Approved-root + relative-subdir enforced; traversal impossible.
- [x] Writes are atomic; no half-written backup is ever listed as valid.
- [x] Manifest with per-file SHA-256; verification detects corruption.
- [x] Backup-id resolution always re-validates containment.
- [x] >95% coverage for `storage.py`.

## Definition of done

`BackupStorage` can atomically persist, verify, list, and delete backups within an approved
root, with tamper detection and no event-loop blocking.

## Validation completed

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy custom_components tests`

## Open questions / discoveries

- `storage.py` translates shared validator failures (`vol.Invalid` from
   `normalize_backup_subdir`) into `WLEDValidationError` at the storage boundary, so callers
   consistently receive integration-level exception types.
- Atomic writes are implemented with a same-root staging directory and `os.replace`; failure
   paths clean staging directories and never expose partial backups as readable/valid.
- Full-suite validation after plan-07 landing is green (`66 passed`), while the existing
   `pytest-asyncio` custom `event_loop` deprecation warning remains a known baseline unrelated
   to storage behavior.

## References

- HA executor offloading: https://developers.home-assistant.io/docs/asyncio_blocking_operations/
- HAOS storage roots (/share, /media, /backup): https://www.home-assistant.io/common-tasks/os/#network-storage
- PRD §4 (manifest), §5 (storage model), §13 (storage service), §15 (integrity), §23 (security).
