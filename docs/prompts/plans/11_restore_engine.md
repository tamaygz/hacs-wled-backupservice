---
goal: Implement safe, sequential restore of WLED config and presets with safety backup and verification
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [restore, safety, destructive]
---

# 11 — Restore engine

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Implement `WLEDBackupManager.async_restore` to validate a backup, optionally take a safety
backup, restore config and/or presets **sequentially** per device, verify, and report
exactly which parts succeeded — treating restore as an explicitly destructive operation.

## Scope

In scope: restore orchestration, safety backup, per-device locking, config + preset restore,
verification, partial-failure reporting. Out of scope: service schema (10), scheduling (12).

## Prerequisites / dependencies

- Plans **06** (client, incl. `set_config`/`upload_presets`), **07** (storage validate),
  **08** (backup for safety copy) complete.

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/restore.py     # or extend manager.py
custom_components/wled_backupservice/manager.py     # async_restore entry point
```

## Detailed implementation tasks

1. `async_restore(device, backup_id, *, backup_before_restore=True, restore_config=True,
   restore_presets=True, verify_after_restore=True, reboot_after_restore=False) -> RestoreResult`.
2. **Acquire the per-device lock** for the entire restore (WLED sequencing).
3. **Validate backup**: `descriptor = await storage.async_read_backup(backup_id)` — parse
   manifest, verify schema version, verify SHA-256 of every file, confirm required artifacts.
   Fail early with `WLEDValidationError`/`WLEDBackupNotFoundError` if invalid/missing.
4. **Verify device identity**: `info = await client.async_get_info()`; compare MAC to the
   backup's device MAC. On mismatch → refuse unless the caller explicitly targeted this
   device (never silently restore one device's backup onto another). Compare firmware
   version and **surface a WARNING** when different (PRD §10) — do not block, but record it.
5. **Safety backup** (default true): before mutating, call `async_backup_device` for the
   target and record the resulting `backup_id` in the result as the rollback point. If the
   safety backup fails, **abort** the restore (do not proceed without a rollback point)
   unless the caller explicitly opts out.
6. **Sequential apply** (never parallel to the same device):
   - If `restore_config`: `await client.async_set_config(cfg)` using the backup's `cfg.json`.
     Preserve unknown fields; do not strip/clean fields (PRD §10). Then verify via
     `/json/cfg` + `/json/info`.
   - If `restore_presets`: `await client.async_upload_presets(presets_bytes)` via the
     `/edit` mechanism. This capability is **version-sensitive** — if the client reports the
     upload path unavailable/unverified for the device, mark presets restore as
     `skipped/unsupported` in the result rather than claiming success (PRD §10, plan 06).
7. **Reboot** (optional, after config restore): `await client.async_reboot()` where the
   firmware supports it and the option is set; note connectivity impact.
8. **Verification** (default true): re-read info/cfg and confirm the applied portions match
   expectations where feasible; presets verification is best-effort (re-GET `/presets.json`
   and compare hash if practical).
9. **Result**: `RestoreResult` with per-portion status (config: ok/failed/skipped, presets:
   ok/failed/skipped/unsupported), safety-backup id, firmware-mismatch flag, and messages.
   Report partial success explicitly; raise a `WLEDRestoreError` only for total failure so
   the service surfaces an error, while partial results are returned via response data.

## API / framework requirements

- `WLEDClient.async_set_config` (`POST /json/cfg`), `async_upload_presets` (`/edit`),
  `async_get_info`/`async_get_config` for verification, optional `async_reboot`.
- `storage.async_read_backup` for validated backup + raw bytes.
- Per-device `asyncio.Lock` from the manager.

## Important technical decisions

- **Restore is destructive** and can change Wi-Fi/MQTT/connectivity and reboot the device;
  the UI/action text must say so (PRD §3.5) — enforced via `services.yaml`/translations.
- **Safety-first**: default to a fresh safety backup and abort if it fails.
- **No fake preset reconstruction** — only real `/edit` upload; if unavailable, report
  unsupported (PRD §10, §33).
- Never restore across device identities silently.
- Preserve unknown config fields; never "clean" config.

## Edge cases (PRD §22 restore suite)

- Valid backup; invalid manifest; hash mismatch; firmware mismatch (warn, proceed);
  backup-before-restore; config-only restore; presets-only restore; sequential requests
  (serialized); partial failure (config ok, presets fail → partial result); verification
  failure; safety-backup failure (abort); preset upload unsupported → skipped.
- Device becomes unreachable mid-restore (e.g. after config change/reboot) → report the
  portion applied and the connectivity note; do not hang.

## Security / safety considerations

- Only integration-generated `backup_id`s, re-resolved inside the root (no arbitrary paths).
- Never write to another device's identity.
- Do not log config/preset payloads or secrets.
- Bounded timeouts; the whole restore holds the device lock to prevent concurrent writes.

## Testing requirements

- All restore-suite edge cases above with mocked client + storage.
- Assert sequential ordering (config before presets; no same-device concurrency).
- Assert abort when safety backup fails (default).
- Assert firmware mismatch produces a warning but proceeds.
- Assert presets-unsupported path yields `skipped/unsupported`, not false success.
- Partial-failure result shape.

## Acceptance criteria

- [x] Backup validated (schema + hashes) before any write.
- [x] Identity verified; cross-device restore refused.
- [x] Safety backup taken by default; abort on its failure.
- [x] Config + presets restored sequentially with per-portion status.
- [x] Preset restore honest about unsupported/unverified firmware.
- [x] >95% coverage for restore code.

## Definition of done

Restore is safe, sequential, validated, and transparent about partial success and preset-
restore limitations, with a rollback safety backup by default.

## Validation completed

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy custom_components tests`

## Open questions / discoveries

- The restore engine landed directly in `manager.py` plus a new `RestoreResult` model and
   storage raw-file read helper; full-suite validation now drives `manager.py` to 96%
   coverage, satisfying the restore-plan coverage gate without a separate `restore.py`
   module.
- Preset restore only reports `ok` when the WLED client marks `/edit` upload support as
   both available and verified; otherwise the result stays honest with
   `presets_status="unsupported"` plus a warning message.
- Restore keeps the per-device lock for the full operation, takes a fresh safety backup by
   default, refuses cross-device MAC mismatches, and downgrades firmware drift to a warning
   rather than a hard block.
- The restore action in `services.py` now returns serialized `RestoreResult` payloads
   instead of the temporary “not available yet” error from plan 10.
- Full-suite validation after plan-11 landing is green (`108 passed`, `manager.py` 96%
   coverage, total coverage 94%). The existing `pytest-asyncio` custom `event_loop`
   deprecation warning remains an unchanged baseline unrelated to restore behavior.

## References

- WLED config POST + presets `/edit` restore: https://kno.wled.ge/interfaces/json-api/ , https://kno.wled.ge/features/presets/
- WLED sequencing guidance: https://kno.wled.ge/interfaces/json-api/
- PRD §10 (restore strategy), §15 (integrity), §16 (errors), §3.4/§3.5 (safety), §33 (cautions).
