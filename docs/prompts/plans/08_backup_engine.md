---
goal: Implement the backup engine that composes discovery, client, and storage into device and bulk backups
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [backup, manager, engine]
---

# 08 — Backup engine

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Implement `WLEDBackupManager.async_backup_device` and `async_backup_all` to verify a device,
fetch the selected artifacts, and persist an atomic, hashed backup, returning a structured
result.

## Scope

In scope: manager backup methods, per-device locking, result model, artifact selection.
Out of scope: retention (09), service exposure (10), restore (11), scheduling (12).

## Prerequisites / dependencies

- Plans **05** (discovery), **06** (client), **07** (storage) complete.

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/manager.py     # implement backup methods
custom_components/wled_backupservice/models.py      # BackupResult / result dataclasses (optional)
```

## Detailed implementation tasks

1. **Per-device lock**: `self._locks[device_id]` (`asyncio.Lock`), lazily created, used for
   all read/write to a single device (WLED sequencing requirement). Backups acquire the lock
   for the device being backed up.
2. `async_backup_device(device, *, include_presets, include_state, label=None) -> BackupResult`:
   - Resolve options defaults from `entry.options` when args are omitted.
   - Build a `WLEDClient` for `device.host` (shared session).
   - **Verify**: `info = await client.async_get_info()`; assert WLED identity
     (`brand == "WLED"` where present) and a usable MAC; on mismatch with the discovered
     MAC, log a warning but proceed using verified identity (record both in manifest).
   - Fetch artifacts: always `cfg = async_get_config()`; if `include_presets`,
     `presets = async_get_presets_raw()`; if `include_state`, `state = async_get_state()`;
     optionally `info.json`.
   - Assemble the file set + device metadata and call `storage.async_write_backup(...)`
     (atomic staging→rename, manifest + hashes).
   - Return `BackupResult(device_id, device_name, success, backup_id, path, files,
     created_at, error=None)`.
3. `async_backup_all(*, ...) -> list[BackupResult]`:
   - `devices = await discovery.async_discover_wled_devices(hass)`.
   - Back up devices **sequentially or with bounded concurrency across distinct devices**,
     but never concurrently to the *same* device. Default to sequential for predictability;
     if concurrency is added, cap it and keep per-device serialization.
   - **Continue on per-device failure**: capture the error into that device's
     `BackupResult(success=False, error=...)` and proceed with the rest (PRD §6).
   - Aggregate and return all results.
4. `async_discover_devices(...)` delegates to `discovery.async_discover_wled_devices`.
5. Logging (PRD §16): INFO on cycle start/success, WARNING on individual device
   unavailable/missing optional artifact/firmware note, ERROR on cycle-level failure. Never
   log payloads/secrets.

## API / framework requirements

- `asyncio.Lock` per device; `homeassistant.util.dt` for timestamps.
- Uses plan 05/06/07 public interfaces only (no reaching into private state).

## Important technical decisions

- **Fail-soft bulk backup**: one bad device never aborts the whole cycle.
- Verification result (not the discovered guess) is authoritative for identity recorded in
  the manifest.
- Backup is **not** retention-coupled: `async_backup_*` only creates; pruning is a separate
  call (plan 09) invoked by the scheduler/service after a successful cycle.

## Edge cases

- Device offline during backup → `success=False`, error captured, others continue.
- `include_presets=True` but presets fetch returns empty/large → handle per plan 06;
  empty presets still recorded (valid) vs. fetch error (failure) — distinguish clearly.
- MAC mismatch between discovery and live `/json/info` → warn + record actual.
- Concurrent backup requests for the same device (e.g. scheduler + manual) → serialized by
  the lock; second waits, does not corrupt.
- Zero discovered devices in `async_backup_all` → empty result list (not an error).

## Security / safety considerations

- Only back up hosts from discovered `wled` entries.
- No secrets/payloads in logs.
- Rely on storage's atomicity + hashing for integrity.

## Testing requirements (PRD §22)

- Mock discovery + client + storage: successful single backup writes expected files +
  manifest.
- `async_backup_all` with a mix of healthy and failing devices → per-device results, cycle
  continues.
- Same-device concurrency serialized by lock (assert no interleaving).
- Identity mismatch produces a warning + correct manifest identity.
- Result model fields populated correctly.

## Acceptance criteria

- [x] Single-device backup verifies, fetches selected artifacts, writes atomically, returns result.
- [x] Bulk backup is fail-soft and per-device serialized.
- [x] Structured `BackupResult` returned for services/response data.
- [x] >95% coverage for the backup paths in `manager.py`.

## Definition of done

The manager can back up one or all discovered WLED devices into valid, hashed, atomic
backups, returning structured results, with robust per-device error isolation.

## Validation completed

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy custom_components tests`

## Open questions / discoveries

- The manager keeps plan-08 wiring lazy and collaborator-driven: `discovery`, `client_factory`,
  and `storage` can be injected directly by tests or later slices, while default wiring only
  occurs when a given collaborator is actually needed.
- Bulk backup is implemented sequentially by design for predictability. Per-device locking is
  still in place so concurrent callers targeting the same device are serialized even if future
  slices introduce broader concurrency.
- The manager records `info.json` alongside `cfg.json` and optional `presets.json` /
  `state.json`, giving later restore or diagnostics work a verified snapshot of the live
  device identity used during backup.
- Full-suite validation after plan-08 landing is green (`82 passed`, total coverage 95%),
  while the existing `pytest-asyncio` custom `event_loop` deprecation warning remains an
  unchanged baseline unrelated to backup-engine behavior.

## References

- WLED sequencing (serialize writes): https://kno.wled.ge/interfaces/json-api/
- PRD §12 (manager), §4 (content), §15 (integrity), §16 (logging), §11 (response data).
