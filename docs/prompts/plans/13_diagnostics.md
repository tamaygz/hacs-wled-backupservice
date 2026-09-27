---
goal: Implement config-entry diagnostics with safe metadata and secret redaction
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [diagnostics, redaction, quality-scale]
---

# 13 — Diagnostics

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Provide `diagnostics.py` exposing safe integration metadata (version, redacted config/
options, discovered devices, backup counts, last success/failure, storage root type,
runtime state) without leaking secrets or backup contents.

## Scope

In scope: `async_get_config_entry_diagnostics`. Out of scope: diagnostic entities (deferred,
PRD §17).

## Prerequisites / dependencies

- Plans **03** (runtime manager) and **08** (backup counts/last-run state) complete.

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/diagnostics.py
custom_components/wled_backupservice/manager.py     # expose last-run/last-error/counters
```

## Detailed implementation tasks

1. Track lightweight runtime state in the manager: `last_backup_success` (ts),
   `last_backup_status`, `last_error` (message only), `discovered_device_count`,
   per-device `backup_count` (from storage list), `storage_root_type`.
2. `async_get_config_entry_diagnostics(hass, entry)` returns a JSON-serializable dict:
   - integration version (from manifest), redacted `entry.data`/`entry.options`,
   - discovered device count + names + firmware versions (names are not secrets, but keep
     hosts/MACs redacted or partially masked),
   - backup counts per device, last success/failure, storage root type, runtime state.
3. **Redaction**: use `homeassistant.components.diagnostics.async_redact_data` to redact any
   sensitive keys (host, mac, tokens if ever present). Never include backup file contents,
   `cfg.json`, `presets.json`, credentials, or network secrets (PRD §18, §23).

## API / framework requirements

- `homeassistant.components.diagnostics.async_redact_data` + a `TO_REDACT` set.
- Diagnostics platform contract: `async_get_config_entry_diagnostics`.

## Important technical decisions

- Diagnostics are **metadata only**; never dump artifacts.
- Prefer partial masking of host/MAC over full removal so support remains useful, but keep
  full secrets out.

## Edge cases

- No backups yet → zero counts, null last-run.
- Discovery fails → report the error message (redacted) without crashing diagnostics.
- Large device lists → include counts + names, not full payloads.

## Security / safety considerations

- Central `TO_REDACT` set; apply to all nested structures.
- Do not read backup file bodies for diagnostics.

## Testing requirements

- Diagnostics output contains expected metadata keys.
- Redaction removes/masks sensitive fields.
- No backup contents present in output.
- Works with zero backups / failed discovery.

## Acceptance criteria

- [x] Diagnostics returns safe metadata + runtime state.
- [x] Secrets redacted; no artifact contents.
- [x] Robust to empty/error states.
- [x] >95% coverage for `diagnostics.py`.

## Definition of done

Config-entry diagnostics provide useful, redacted operational metadata suitable for issue
reports, leaking no secrets or backup contents.

## Validation completed

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy custom_components tests`

## Open questions / discoveries

- Diagnostics landed as the standard top-level integration module in
  `custom_components/wled_backupservice/diagnostics.py`; no extra manifest hook or platform
  registration was required for config-entry diagnostics in this repo shape.
- The manager now exposes lightweight runtime metadata for diagnostics: discovered-device
  count, last backup status, last successful backup timestamp, last error message, and the
  current integration version loaded from `manifest.json`.
- Diagnostics redact `entry.data` and `entry.options` with Home Assistant's
  `async_redact_data`, while discovered-device and backup inventory sections expose only
  partially masked host/MAC/device identifiers plus safe metadata such as names, firmware,
  counts, and timestamps.
- Backup artifact contents are never loaded for diagnostics; backup counts and latest backup
  timestamps come from validated storage descriptors returned by `async_list_backups()`.
- Full-suite validation after plan 13 is green (`118 passed`, `ruff check .`, and
  `mypy custom_components tests`), with `diagnostics.py` at 100% coverage. The existing
  `pytest-asyncio` custom `event_loop` deprecation warning remains an unchanged baseline.

## References

- HA diagnostics: https://developers.home-assistant.io/docs/core/integration_diagnostics/
- PRD §18 (diagnostics), §23 (security), §17 (optional entities).
