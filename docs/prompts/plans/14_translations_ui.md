---
goal: Author custom-integration translations and polish all user-facing UI strings
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [translations, i18n, ui]
---

# 14 — Translations & UI polish

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Provide a complete, flat `translations/en.json` covering config/options flow, services,
exceptions, and any entity/diagnostic strings, plus polished `data_description` help text —
following custom-integration localization rules.

## Scope

In scope: `translations/en.json`, optional `strings.json` (authoring source), review of all
`services.yaml` text. Out of scope: adding new features.

## Prerequisites / dependencies

- Plans **04** (config/options keys), **10** (service names/fields), **11** (restore
  messages) complete so all keys exist.

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/translations/en.json
custom_components/wled_backupservice/strings.json     # optional authoring copy (NOT used at runtime)
custom_components/wled_backupservice/services.yaml    # ensure names/descriptions align
```

## Detailed implementation tasks

1. **Critical rule**: For custom integrations you must **manually** ship
   `translations/en.json` with the **full flat English text for every key**. `strings.json`
   is **not** processed at runtime for custom integrations — if kept, it is only an authoring
   source and must be copied into `translations/en.json`. Do not rely on core `strings.json`
   behavior.
2. Populate translation sections:
   - `config`: step titles/descriptions, `data`, `data_description`, `abort`
     (`single_instance_allowed`), `error` messages.
   - `options`: section titles + `data`/`data_description` for Schedule/Storage/Contents/
     Retention/Behavior; include the `/backup` = HA backup mount note; path-traversal and
     invalid-interval error strings.
   - `services`: names + descriptions + field descriptions (mirror `services.yaml`).
   - `exceptions`: translated messages for `WLEDBackup*` `translation_key`s used in
     services/restore.
   - `entity`/`selector` sections if any selector option labels need translating.
3. Ensure every `translation_key`/`data_description` referenced in code exists in
   `en.json` (no missing keys). Add a test that cross-checks.
4. Make destructive-restore warnings explicit in the `restore` service description and the
   options behavior section (PRD §3.5).

## API / framework requirements

- Custom-integration localization: manual flat `translations/en.json`.
- `services.yaml` + translation `services` section for Actions UI.

## Important technical decisions

- `translations/en.json` is authoritative at runtime; `strings.json` optional.
- Keep keys flat and complete; missing keys degrade the UI to raw key names.

## Edge cases

- A code-referenced key missing from `en.json` → UI shows the raw key; the cross-check test
  must catch this.
- Adding a new language later → copy `en.json` structure to `<lang>.json`.

## Security / safety considerations

- No secrets in strings; restore warnings must clearly state connectivity/reboot risk.

## Testing requirements

- Parse `en.json`; assert it is valid JSON and flat.
- Cross-check: every `translation_key` and `data_description` referenced in code/`services.yaml`
  exists in `en.json`.
- Assert the `restore` description contains an explicit destructive/connectivity warning.

## Acceptance criteria

- [x] `translations/en.json` complete and flat for all keys.
- [x] Config/options/services/exceptions all covered.
- [x] Destructive-restore warning present.
- [x] Cross-check test passes.

## Definition of done

All user-facing text renders correctly in the HA UI from `translations/en.json`, with no
missing keys and clear destructive-action warnings.

## Validation completed

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy custom_components tests`

## Open questions / discoveries

- This repo now ships both `strings.json` and `translations/en.json` with identical flat
  English content. Runtime remains driven by `translations/en.json`, while `strings.json`
  serves as an authoring copy that stays in sync through the translation cross-check test.
- `config_flow.py` now uses selector translation keys for the interval-unit and storage-root
  dropdowns, so those options render polished labels instead of raw internal values.
- The restore warning is carried in the translated service description and the options
  behavior-step description: restore is explicitly marked destructive, may affect
  connectivity, and may reboot the device.
- There are still no code-level `translation_key` consumers for custom exception classes, so
  no dedicated `exceptions` translation section was required yet; the cross-check test
  confirms all currently referenced config/options/service keys are present.
- Full-suite validation after plan 14 is green (`121 passed`, `ruff check .`, and
  `mypy custom_components tests`), with the new translation cross-check test passing and the
  existing `pytest-asyncio` custom `event_loop` deprecation warning unchanged.

## References

- Custom integration localization: https://developers.home-assistant.io/docs/internationalization/custom_integration
- Config flow translations: https://developers.home-assistant.io/docs/core/integration/config_flow/#translations
- PRD §7 (UI), §16 (error translations), §3.5 (restore warnings), §19 (translation note).
