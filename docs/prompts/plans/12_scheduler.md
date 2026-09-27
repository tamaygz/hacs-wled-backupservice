---
goal: Implement native, non-overlapping scheduled backups driven by the options flow
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [scheduler, automation, lifecycle]
---

# 12 — Scheduler

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Run scheduled backups using HA's scheduling helpers (not a `while True` loop), honoring the
options-flow schedule, guaranteeing no overlapping cycles, and pruning after success.

## Scope

In scope: scheduler wiring inside the manager, interval/daily handling, overlap guard,
prune-after-backup. Out of scope: the backup/prune logic itself (08/09).

## Prerequisites / dependencies

- Plans **08** (backup_all), **09** (prune) complete. Integrates with lifecycle (03) and
  options (04).

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/manager.py     # scheduler setup/teardown + cycle runner
custom_components/wled_backupservice/scheduler.py   # optional helper module
```

## Detailed implementation tasks

1. On `manager.async_setup()` (called from `async_setup_entry`), read schedule options and
   register a time trigger:
   - Unit `minutes`/`hours`/`days` with numeric interval → `async_track_time_interval`
     with the computed `timedelta`.
   - Unit `days` **with a `daily_time`** → `async_track_time_change` at that time (daily),
     which is more predictable than an interval for "daily at HH:MM".
   - Store the unsub callback; register it via `entry.async_on_unload` and clear it in
     `async_shutdown()`.
   - If `schedule_enabled` is false, register nothing.
2. **Overlap guard**: a manager-level `asyncio.Lock` or boolean `self._cycle_running`. When
   a scheduled tick fires while a cycle is still running, **skip** (log at DEBUG/INFO) rather
   than queueing/overlapping (PRD §6).
3. **Cycle runner** `async_run_scheduled_cycle()`:
   - `results = await async_backup_all(...)` using current options for contents.
   - After the cycle, `await async_prune()` (retention) — only after backups complete.
   - Log a per-device summary (success/failure counts). Continue past individual failures
     (already handled in 08).
4. **Reload behavior**: options changes reload the entry (plan 03 update listener), which
   tears down and re-creates the scheduler with new settings — no manual diffing needed.
5. Use `entry.async_create_background_task` for the running cycle so it is tracked and
   cancelled on unload; ensure cancellation doesn't corrupt an in-flight atomic write
   (storage rename is the commit point; a cancelled staging write leaves no valid backup).

## API / framework requirements

- `homeassistant.helpers.event.async_track_time_interval` /
  `async_track_time_change`.
- `entry.async_on_unload`, `entry.async_create_background_task`.
- `homeassistant.util.dt` for time handling / timezones.

## Important technical decisions

- **No custom infinite loop** (PRD §6, §33) — use HA helpers so unload/reload/restart behave.
- Prefer `async_track_time_change` for daily-at-time; `async_track_time_interval` otherwise.
- Skip-on-overlap (do not queue) to avoid pile-ups on slow networks.

## Edge cases

- HA restart mid-schedule → next tick reschedules cleanly (no persistence of missed runs in
  v1; document).
- Options change during a running cycle → reload tears down scheduler; the in-flight cycle's
  background task is cancelled on unload; partial atomic writes leave no valid backup.
- `schedule_enabled=false` → no trigger registered.
- Very short intervals (e.g. minutes) with many devices → overlap guard prevents pile-up.
- DST / timezone transitions for daily time → rely on HA dt helpers.

## Security / safety considerations

- Scheduled cycles use the same safe backup/prune paths; no new attack surface.
- Ensure teardown always removes the time listener (no leaks across reloads).

## Testing requirements

- Interval scheduling triggers a cycle (advance HA test clock; assert `backup_all` called).
- Daily-time scheduling triggers at the configured time.
- Overlap guard: a tick during a running cycle is skipped.
- Disabled schedule registers no trigger.
- Unload/reload removes and re-adds the listener (no leak; no double-fire).
- Prune runs after a successful cycle.

## Acceptance criteria

- [x] Uses HA scheduling helpers; no infinite loop.
- [x] Interval and daily-at-time both supported.
- [x] No overlapping cycles.
- [x] Prune runs after successful backups.
- [x] Clean teardown on unload/reload.
- [x] >95% coverage for scheduler code.

## Definition of done

Scheduled backups run per the options configuration, never overlap, prune afterward, and
tear down cleanly on unload/reload/restart.

## Validation completed

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy custom_components tests`

## Open questions / discoveries

- The scheduler landed directly inside `manager.py`: `async_setup()` now registers either
  `async_track_time_interval` or `async_track_time_change`, `async_shutdown()` tears the
  listener down, and scheduled runs are launched with `entry.async_create_background_task`
  so Home Assistant cancels them automatically during unload.
- Because the options flow always carries both `interval` and `daily_time`, the runtime
  treats `daily_time` as the explicit daily trigger only when the schedule is exactly
  `1 day`; multi-day schedules continue to use interval timing so “every 2 days” remains
  expressible.
- Overlap protection is implemented as a tracked background task reference: if a previous
  scheduled cycle is still running when the next tick fires, the tick is skipped rather
  than queued.
- Scheduled cycles reuse the existing backup and retention paths, passing the current
  `include_presets` / `include_state` options into `async_backup_all()` and pruning only
  after the backup pass completes.
- Full-suite validation after plan 12 is green (`114 passed`, `ruff check .`, and
  `mypy custom_components tests`), with `manager.py` at 95% coverage. The existing
  `pytest-asyncio` custom `event_loop` deprecation warning remains an unchanged baseline.

## References

- HA event helpers: https://developers.home-assistant.io/docs/api/core/#tracking-time
- PRD §6 (scheduling), §33 (no infinite loop).
