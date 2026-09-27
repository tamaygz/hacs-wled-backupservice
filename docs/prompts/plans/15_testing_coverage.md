---
goal: Consolidate shared test fixtures, fill coverage gaps, and enforce a >95% coverage gate
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Planned'
tags: [testing, coverage, fixtures]
---

# 15 — Testing & coverage gate

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

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

- [ ] Coverage >95% for integration code, gate enforced in config.
- [ ] Shared fixtures + realistic WLED fixtures present.
- [ ] End-to-end test passes.
- [ ] No network / no blocking-I/O in tests.

## Definition of done

The suite comprehensively covers the integration at >95% with an enforced gate, shared
fixtures, and an end-to-end scenario, all offline.

## References

- pytest-homeassistant-custom-component: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component
- HA blocking-I/O detection: https://developers.home-assistant.io/docs/asyncio_blocking_operations/
- PRD §22 (testing requirements).
