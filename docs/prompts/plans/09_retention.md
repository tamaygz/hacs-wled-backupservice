---
goal: Implement safe count-based and age-based retention pruning of backups per device
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Planned'
tags: [retention, pruning, storage]
---

# 09 — Retention policy

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Objective

Implement `retention.py` + `WLEDBackupManager.async_prune` to enforce count-based (primary)
and optional age-based retention per device, deleting only confidently identified backups.

## Scope

In scope: retention algorithm, `async_prune`, dry-run support. Out of scope: scheduling the
prune (12), service exposure (10) — they call this.

## Prerequisites / dependencies

- Plans **07** (storage list/delete + manifest) and **08** (backup layout) complete.

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/retention.py
custom_components/wled_backupservice/manager.py     # implement async_prune delegating to retention
```

## Detailed implementation tasks

1. Read policy from `entry.options`: `retention_count` (primary), `retention_days`
   (secondary). `0` for both means **keep all** (PRD §7/§4 edge case).
2. Algorithm (PRD §14), per device:
   - Enumerate **valid** backup descriptors via `storage.async_list(device)` (only dirs with
     a parseable, supported manifest count).
   - Sort by manifest `created_at` (not directory name).
   - **Count**: keep newest `retention_count`; mark older for deletion.
   - **Age**: additionally mark entries older than `retention_days` for deletion.
   - Never mark an entry that cannot be confidently identified as this integration's backup.
3. `async_prune(*, device=None, dry_run=False) -> PruneResult`:
   - Scope to one device or all discovered/known device dirs.
   - In `dry_run`, return the would-delete list without deleting.
   - Otherwise delete via `storage.async_delete(backup_id)` (root-confined), collecting
     successes/failures; continue on individual failure.
   - Return a structured `PruneResult` (per-device kept/deleted counts + ids).
4. Retention runs **after** a successful backup cycle (called by scheduler/service), never
   before writing a new backup.

## API / framework requirements

- Uses `storage.async_list`/`async_delete` (root-confined) and manifest `created_at`.
- `homeassistant.util.dt` for age comparison (tz-aware).

## Important technical decisions

- **Count-based is primary** (PRD requirement: "how many backups to save"); age is an
  optional second safeguard.
- Malformed/unrecognized directories are **immutable** to retention.
- Prune is idempotent and safe to run repeatedly.

## Edge cases (PRD §22)

- Fewer backups than `retention_count` → delete nothing.
- `retention_count = 0` and `retention_days = 0` → keep all.
- Only age set (count 0) → age-only pruning.
- Corrupt/foreign directory present → never deleted; logged at WARNING.
- Deletion failure for one entry → others still processed.
- Timezone-naive vs aware timestamps → normalize before comparison.

## Security / safety considerations

- All deletions go through storage's root-confined delete (no path escape).
- Confidence gate prevents deleting user data that isn't ours.

## Testing requirements

- Count retention keeps newest N, deletes the rest (sorted by manifest time).
- Age retention deletes only entries older than M days.
- Combined policy.
- Keep-all when both zero.
- Foreign/corrupt dir untouched.
- Dry-run deletes nothing but reports correctly.
- Per-entry delete failure does not abort the run.

## Acceptance criteria

- [ ] Count-based retention correct and primary.
- [ ] Optional age-based retention correct.
- [ ] Never deletes unrecognized/foreign directories.
- [ ] Dry-run supported.
- [ ] >95% coverage for `retention.py`.

## Definition of done

Retention prunes only this integration's backups per the configured policy, safely and
idempotently, with a dry-run mode, and is invoked after successful backups.

## References

- PRD §14 (retention), §5 (layout), §15 (integrity), §23 (security).
