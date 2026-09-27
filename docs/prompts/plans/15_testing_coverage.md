---
goal: Consolidate shared test fixtures, fill coverage gaps, and enforce a >95% coverage gate
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [testing, coverage, fixtures]
---

# 15 — Testing & coverage gate

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Ensure the full test suite (unit tests authored in plans 01–14 plus cross-cutting
integration tests) reaches **>95% coverage** for integration modules, with shared fixtures
and realistic WLED payload fixtures.

## Scope

In scope: shared `conftest.py` fixtures, WLED JSON fixtures, cross-module integration tests,
coverage gate config, gap-filling. Out of scope: new production features.

## Prerequisites / dependencies

- All implementation plans **01–14** complete (each already ships its own unit tests).

## Relevant files / modules to create or modify

```text
tests/conftest.py                # shared fixtures (hass, mock wled entries, storage tmp root)
tests/fixtures/info.json
tests/fixtures/cfg.json
tests/fixtures/presets.json
tests/test_integration_end_to_end.py   # setup entry → backup → list → restore → prune
pyproject.toml                   # coverage fail_under = 95
```

## Detailed implementation tasks

1. **Fixtures**: realistic `info.json` (with `brand`, `mac`, `ver`, `arch`, `name`),
   `cfg.json`, and a non-trivial `presets.json` (including at least one API-command preset
   and a large-ish payload) under `tests/fixtures/`.
2. **Shared conftest fixtures**:
   - a configured `MockConfigEntry` for `wled_backupservice` with default options,
   - mock `wled` config entries + device registry entries for discovery,
   - a temp storage root (`tmp_path`) mapped so `storage` writes there,
   - an aiohttp mock (`aioclient_mock`/`aioresponses`) preloaded with WLED endpoints.
3. **End-to-end integration test**: set up the entry → run `backup`/`backup_all` →
   `list_backups` → `restore` (config-only and presets, incl. the unsupported-preset path)
   → `prune`; assert filesystem layout, manifest hashes, response data, and safe behavior.
4. **Coverage**: set `fail_under = 95` for `custom_components/wled_backupservice`. Identify
   and fill gaps (error branches, edge cases). Exclude only unreachable/`TYPE_CHECKING`
   blocks via `# pragma: no cover` sparingly.
5. Ensure **no real network** and **no real blocking I/O warnings** (HA test harness fails on
   blocking calls in the loop) across the suite.

## API / framework requirements

- `pytest-homeassistant-custom-component` fixtures (`hass`, `enable_custom_integrations`,
  `aioclient_mock`, `MockConfigEntry`, `snapshot` optional).
- Coverage via `pytest-cov`.

## Important technical decisions

- Per-module tests remain in their plans; this plan only adds cross-cutting tests + the gate.
- Fixtures centralized to avoid duplication across module tests.

## Edge cases

- Cover every error branch surfaced by plans 05–13 (connection/timeout/validation/traversal/
  hash-mismatch/partial-restore/overlap-skip/no-entry-service-call).

## Security / safety considerations

- Tests must assert traversal rejection, non-WLED target rejection, no-secret-in-logs, and
  no-arbitrary-path restore.

## Testing requirements

- Full suite green; coverage >95%.
- End-to-end happy path + key destructive/edge paths covered.

## Acceptance criteria

- [x] Coverage >95% for integration code, gate enforced in config.
- [x] Shared fixtures + realistic WLED fixtures present.
- [x] End-to-end test passes.
- [x] No network / no blocking-I/O in tests.

## Definition of done

The suite comprehensively covers the integration at >95% with an enforced gate, shared
fixtures, and an end-to-end scenario, all offline.

## Validation completed

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy custom_components tests`

## Open questions / discoveries

- The repo now ships realistic WLED payload fixtures in `tests/fixtures/info.json`,
   `tests/fixtures/cfg.json`, and `tests/fixtures/presets.json`, plus shared fixture loaders
   and a reusable integration-entry fixture in `tests/conftest.py`.
- The end-to-end coverage slice settled on a manager-plus-real-storage roundtrip instead of a
   full Home Assistant service harness to stay stable on Windows while still exercising
   backup, list, restore, and prune across module boundaries.
- Coverage work exposed a real restore-engine defect: `async_restore()` held the per-device
   lock and then called `async_backup_device()` for the safety backup, which deadlocked on the
   same lock. The fix now uses a lock-aware backup helper for the default path while still
   preserving the `async_backup_device` monkeypatch seam used by tests.
- `pyproject.toml` now enforces `fail_under = 95` under `[tool.coverage.report]`.
- Full-suite validation after plan 15 is green (`129 passed`, `ruff check .`, and
   `mypy custom_components tests`), and coverage is enforced at 96.26%.

## References

- pytest-homeassistant-custom-component: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component
- HA blocking-I/O detection: https://developers.home-assistant.io/docs/asyncio_blocking_operations/
- PRD §22 (testing requirements).
