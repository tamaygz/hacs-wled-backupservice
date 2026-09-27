---
goal: Implement a single-instance config flow and a full options flow for schedule, storage, contents, retention, and behavior
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [config-flow, options-flow, ui]
---

# 04 — Config flow & options flow

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Let the user add the integration once via the UI with minimal defaults, then adjust all
behavior later via a sectioned options flow, using selectors and validation.

## Scope

In scope: `config_flow.py` (config + options), option schema, validation helpers, wiring
of translation keys (strings authored in plan 14). Out of scope: applying options to actual
backups (08+), scheduler (12).

## Prerequisites / dependencies

- Plan **03** complete (lifecycle + `const` option keys).

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/config_flow.py
custom_components/wled_backupservice/const.py        # add any missing option keys/defaults
```

## Detailed implementation tasks

1. **Config flow** (`ConfigFlow(domain=DOMAIN)`):
   - `async_step_user`: single informational + minimal-defaults step. Because
     `single_config_entry: true` is set, call `self._async_abort_entries_match()` /
     rely on HA to block a second entry; explicitly `async_abort(reason="single_instance_allowed")`
     if an entry already exists.
   - Create the entry with sensible defaults in `data` (mostly empty — connection-less
     integration) and seed **options** with defaults from `const` (schedule enabled,
     interval 24h, retention 30, storage root `share`, subdir `wled_backups`, include
     presets true). Keep user-visible fields minimal per PRD §7.2; everything else defaults.
   - Set `VERSION = 1`.
2. **Options flow** — **critical API rule**: do **not** implement
   `__init__(self, config_entry)` and do **not** assign `self.config_entry`. Access the
   entry via the auto-injected read-only `self.config_entry`. Implement
   `async_get_options_flow` on the config flow returning the options-flow handler.
   Structure the options into steps or a single schema with `section`s:
   - **Schedule**: `schedule_enabled` (bool), `interval` (int > 0), `interval_unit`
     (select: minutes/hours/days), `daily_time` (TimeSelector, only meaningful when unit =
     days).
   - **Storage**: `storage_root` (select from `share/media/backup/config`), `subdir`
     (text, relative only).
   - **Contents**: `include_presets` (bool), `include_state` (bool, default false),
     `create_archive` (bool, optional).
   - **Retention**: `retention_count` (int ≥ 0), `retention_days` (int ≥ 0; 0 = disabled).
   - **Behavior**: `backup_before_restore` (bool, default true), `verify_after_restore`
     (bool), `reboot_after_restore` (bool).
   - Use `selector` helpers (`SelectSelector`, `NumberSelector`, `BooleanSelector`,
     `TimeSelector`, `TextSelector`). Prefill defaults from existing `self.config_entry.options`.
3. **Validation** (raise `vol.Invalid` / return `errors` dict):
   - `subdir` must be relative (reject leading `/`, drive letters, and any `..` segment).
     Normalize with `PurePosixPath` and reject traversal. This is the same rule enforced by
     the storage layer (plan 07) — centralize the check in a small helper importable by both.
   - `interval` must be a positive integer; `retention_count`/`retention_days` must be ≥ 0.
   - Selecting `storage_root = backup` should surface the note that `/backup` is HA's
     backup-storage mount (translation string in plan 14).
4. On options submit, store the flat options dict; the update listener (plan 03) reloads
   the entry so the scheduler picks up changes.

## API / framework requirements

- `homeassistant.helpers.selector` for all inputs (SelectSelector, NumberSelector,
  BooleanSelector, TimeSelector, TextSelector).
- `voluptuous` schema with `vol.Required`/`vol.Optional` and defaults from options.
- Options flow uses the **auto-injected `self.config_entry`** (HA ≥ 2024.11; mandatory
  ≥ 2025.12). Do not set it manually.
- `data_description` keys map to translation file (plan 14).

## Important technical decisions

- Keep initial setup nearly zero-question; push configuration into options (PRD §7).
- Centralize the relative-path/traversal validation helper so config flow and storage share
  one implementation (avoid divergent validation).
- Use `section`s or multi-step; either is acceptable — pick multi-`section` single-step for
  fewer round-trips unless translation ergonomics favor steps.

## Edge cases

- Empty `subdir` → default to `wled_backups`.
- `interval_unit = days` with no `daily_time` → run at a default time (document behavior).
- Re-adding integration when one already exists → abort with `single_instance_allowed`.
- Options with `retention_count = 0` and `retention_days = 0` → treated as "keep all"
  (document; retention plan 09 must honor this).

## Security / safety considerations

- Reject absolute paths, drive letters, and `..` in `subdir` at the flow boundary (defense
  in depth; storage re-validates).
- Never accept an arbitrary absolute filesystem root — only the four approved roots.

## Testing requirements (PRD §22 config-flow suite)

- Initial setup creates one entry with expected default options.
- Second setup attempt aborts (`single_instance_allowed`).
- Options flow: happy path persists all sections.
- Invalid `subdir` (`../x`, `/abs`, `C:\\x`) rejected with an error.
- Invalid `interval` (0, negative) rejected.
- Options flow does **not** set `self.config_entry` (regression guard: instantiate handler
  and assert no `__init__` override assigns it; or assert setup on HA test version ≥ floor).
- Reload occurs after options change.

## Acceptance criteria

- [x] Integration can be added exactly once via UI with no connection questions.
- [x] Options flow exposes Schedule/Storage/Contents/Retention/Behavior with selectors.
- [x] Path traversal and invalid inputs rejected.
- [x] Options flow uses auto-injected `config_entry` when available and a legacy-compatible helper on the pinned HA test version.
- [x] >95% coverage for `config_flow.py`.

## Definition of done

A user can install, add once, and reconfigure everything via the UI; invalid input is
rejected; config-flow tests pass.

## Validation completed

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy custom_components tests`

## Open questions / discoveries

- The repository's pinned Home Assistant version (`2024.3.3`) predates the 2024.11
  auto-injected `OptionsFlow.config_entry` property. The implemented flow therefore uses a
  compatibility split: a legacy `OptionsFlowWithConfigEntry` path for the current dev stack
  and a future-safe auto-injected path for newer Home Assistant releases.
- The options flow is implemented as a multi-step sequence rather than a single sectioned
  form because that is more stable across the pinned HA selector APIs and keeps validation
  localized per concern.
- Windows Home Assistant flow tests required two harness adjustments in the repo-local test
  stack: `pytest-asyncio` had to run in `auto` mode, and `tzdata` had to be present in the
  repo-local venv so the HA fixture could resolve `US/Pacific`.
- The current Windows async test harness still uses a local `event_loop` override to enable
  sockets during loop creation under `pytest-socket`. It passes today but emits a
  `pytest-asyncio` deprecation warning and should be revisited in a later infrastructure
  cleanup if the project wants a warning-free suite.

## References

- Options flow new properties (config_entry auto-injection): https://developers.home-assistant.io/blog/2024/11/12/options-flow/
- Config flow: https://developers.home-assistant.io/docs/data_entry_flow_index/ and https://developers.home-assistant.io/docs/config_entries_config_flow_handler/
- Selectors: https://www.home-assistant.io/docs/blueprint/selectors/
- Single config entry: https://developers.home-assistant.io/docs/config_entries_index/#single-config-entry
- PRD §7 (config/options flow), §5 (storage options), §6 (schedule).
