---
goal: Master execution index for the WLED Backup Service HACS integration implementation
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'In Progress'
tags: [index, roadmap, home-assistant, hacs, wled]
---

# 0 — Master Execution Index

![Status: In%20Progress](https://img.shields.io/badge/status-In%20Progress-yellow)

## Project overview

`hacs-wled-backupservice` is a **native Home Assistant custom integration** (domain
`wled_backupservice`), distributed through HACS, that provides scheduled and
on-demand **backup / restore / retention** for WLED devices already configured in
Home Assistant's native `wled` integration.

Architectural goal: behave like a normal HA **service integration** — a single config
entry, UI-driven config/options flows, HA Actions (services) with response data, native
scheduling helpers, executor-offloaded filesystem I/O, and no add-on / Docker /
Supervisor / YAML / manual IP list. It reuses HA's `wled` config entries for device
discovery and talks to WLED devices over the documented JSON API + `/edit` filesystem
endpoint.

```text
Home Assistant ──▶ WLED Backup Service
                        │
        ┌───────────────┼───────────────┐
   Config/Options    HA Actions     Scheduler
        └───────────────┼───────────────┘
                 WLEDBackupManager
        ┌───────────────┼───────────────┐
   Discovery       WLEDClient       Storage ──▶ /share|/media|/backup|/config
   (wled entries)  (JSON + /edit)   (atomic + manifest/sha256)
                                        │
                                    Retention
```

## Execution order

| #  | Plan                                                                              | Status         | Depends on | Notes |
|----|-----------------------------------------------------------------------------------|----------------|------------|-------|
| 01 | [Repository bootstrap & tooling](01_repository_bootstrap.md)                       | ✅ Complete   | —          | Repo scaffold, repo-local `.venv-py311`, smoke test, Ruff, and mypy all pass |
| 02 | [Manifest, HACS metadata, branding, foundations](02_manifest_hacs_foundations.md) | ✅ Complete   | 01         | `manifest.json`, `hacs.json`, `const.py`, `exceptions.py`, and HACS repo branding placeholder are in place |
| 03 | [Integration skeleton & lifecycle](03_integration_skeleton_lifecycle.md)          | ✅ Complete   | 02         | `__init__.py`, typed `runtime_data`, manager shell, service-registration stub, and lifecycle tests all pass |
| 04 | [Config flow & options flow](04_config_options_flow.md)                            | ✅ Complete   | 03         | Single-instance config flow, multi-step options flow, shared subdir validation, and >95% `config_flow.py` coverage validated |
| 05 | [WLED discovery adapter](05_wled_discovery.md)                                     | ✅ Complete   | 03         | `discovery.py` maps `wled` config entries to stable devices and resolves HA device targets safely |
| 06 | [Async WLED client](06_wled_client.md)                                             | ✅ Complete   | 02         | `wled_client.py` covers typed reads, write error mapping, `/edit` multipart upload, and >95% file coverage |
| 07 | [Storage service](07_storage_service.md)                                           | ✅ Complete   | 02         | `storage.py` now enforces root containment, atomic stage→replace writes, manifest verification, and backup-id revalidation |
| 08 | [Backup engine](08_backup_engine.md)                                               | ✅ Complete   | 05,06,07   | Manager now composes discovery, client, and storage into fail-soft per-device backups with structured results |
| 09 | [Retention policy](09_retention.md)                                                | ✅ Complete   | 07,08      | `retention.py` now applies count/age pruning safely with dry-run and fail-soft delete reporting |
| 10 | [Services / actions registration](10_services_actions.md)                          | ✅ Complete   | 08,09      | All seven actions are registered, target-safe, response-capable, and validated with `services.py` at 97% coverage |
| 11 | [Restore engine](11_restore_engine.md)                                             | ✅ Complete   | 06,07,08   | Safety-backed cfg + presets restore is live, target-safe, and validated with `manager.py` at 96% coverage |
| 12 | [Scheduler](12_scheduler.md)                                                       | ✅ Complete   | 08,09      | HA-native interval/daily scheduling is live with tracked background tasks, skip-on-overlap, and post-cycle prune |
| 13 | [Diagnostics](13_diagnostics.md)                                                   | ✅ Complete   | 03,08      | Redacted config-entry diagnostics are live with masked device metadata, backup counts, and runtime state |
| 14 | [Translations & UI polish](14_translations_ui.md)                                  | ✅ Complete   | 04,10,11   | Flat runtime translations are live with selector labels, restore warnings, and a translation cross-check test |
| 15 | [Testing & coverage gate](15_testing_coverage.md)                                  | ⬜ Not started | all above  | Cross-cutting fixtures, coverage >95%, gap-filling |
| 16 | [CI, Hassfest & HACS validation](16_ci_validation.md)                             | ⬜ Not started | 15         | GitHub Actions: hassfest, HACS action, tests |
| 17 | [Documentation & release](17_documentation_release.md)                            | ⬜ Not started | 16         | README, info.md, quality_scale, GitHub release |

Statuses: ⬜ Not started · 🟡 In progress · ✅ Complete · 🔴 Blocked

## Current checkpoint

- Plans 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, and 14 are complete. The next eligible plan is 15.

## Dependency overview

- **01 → 02 → 03** form the load-bearing foundation: after 03 the integration must be
  installable and loadable by HA (empty but valid).
- **04 (config/options)** and **05 (discovery)** both depend only on 03 and can proceed in
  parallel.
- **06 (client)** and **07 (storage)** depend only on 02 (const/exceptions) and can be
  built independently and in parallel.
- **08 (backup engine)** is the integration point: it needs discovery (05), client (06),
  and storage (07).
- **09 (retention)** needs storage (07) and the backup layout defined in 08.
- **10 (services)** exposes 08 + 09 to the user; **11 (restore)** needs client + storage +
  the backup format from 08; **12 (scheduler)** drives 08 + 09.
  - **Ordering caveat:** the `restore` **action** (plan 10) calls the restore **engine**
    (plan 11). Implement the non-restore actions (backup/backup_all/list/delete/prune/
    discover) in plan 10, then land plan 11 and wire the `restore` action body — or complete
    plan 11 before finishing plan 10's `restore` handler. All other actions have no such
    dependency.
- **13 (diagnostics)**, **14 (translations)** are polish layers over the working feature.
- **15 → 16 → 17** are the release-quality gates.

Each implementation plan (01–14) **includes and requires its own unit tests**. Plan 15 is
not the only place tests are written — it consolidates shared fixtures, enforces the
coverage gate, and fills any gaps.

## Recent discoveries

- For early lifecycle slices on Windows, plain unit tests with explicit `socket_enabled`
  coverage are more stable than full `hass`-fixture tests under
  `pytest-homeassistant-custom-component` because event-loop creation can trip the socket
  guard before the actual lifecycle code is exercised.
- For Home Assistant flow tests on Windows in this repo, `pytest-asyncio` must run in
  `auto` mode and the repo-local venv must include `tzdata`; otherwise the plugin's async
  `hass` fixture either does not resolve correctly or fails while setting the default
  `US/Pacific` timezone.
- Plan 04 uses a version-compatibility split for options flows because the repo's pinned HA
  version (`2024.3.3`) predates the auto-injected `OptionsFlow.config_entry` property that
  became the forward-safe pattern in HA 2024.11+.
- Plan 05 uses a similar compatibility split inside `discovery.py`: newer scoped device
  registry lookups are preferred when present, but the pinned HA stack still requires a
  fallback to `DeviceRegistry.async_get_device(...)` plus config-entry ownership filtering.
- Plan 06 implements preset restore against `/edit` with multipart field name `data` and
  filename `presets.json`, but still marks that capability as unverified until real-firmware
  integration coverage is added during restore work.
- Plan 07 hardens storage error consistency by translating shared validator exceptions
  (`vol.Invalid`) to integration-level `WLEDValidationError`, and validates atomic staging
  cleanup plus manifest/hash integrity with dedicated storage tests (`storage.py` at 98%
  coverage).
- Plan 08 keeps manager wiring lazy and injection-friendly while still wiring default
  discovery/client/storage collaborators when needed. Backups run sequentially across
  devices today, with per-device locks preventing same-device overlap and `BackupResult`
  dataclasses now carrying structured outcome data for later service exposure.
- Plan 09 adds safe retention pruning as a pure storage-backed operation: count is primary,
  age is an optional secondary filter, deletes are fail-soft, and dry-run reporting is
  available through structured `PruneResult` data.
- Plan 10 keeps service registration independent from loaded entries and serializes all
  response payloads to plain dict/list structures.
- Plan 11 implements restore directly in `manager.py` with safety backup by default,
  per-device serialization, cross-device MAC refusal, firmware-drift warnings, and honest
  `unsupported` reporting when preset upload is unavailable or unverified.
- Plan 12 keeps scheduling inside the manager and uses HA-native listeners plus
  `entry.async_create_background_task` for tracked cycles. Because the options flow always
  stores both `interval` and `daily_time`, runtime treats `daily_time` as the daily trigger
  only for `1 day`; larger day-based schedules stay interval-driven.
- Plan 13 adds top-level config-entry diagnostics with Home Assistant redaction for config
  data/options, partial masking for discovered-device and backup inventory metadata, and no
  backup artifact body reads. The manager now tracks lightweight backup runtime state for
  diagnostics and passes the current manifest version into storage.
- Plan 14 adds flat custom-integration translations in both `translations/en.json` and
  `strings.json`, selector labels for options-flow dropdowns, explicit destructive restore
  warnings, and a cross-check test that verifies current config/options/service keys are all
  present in the shipped English text.
- Full-suite validation after plan 14 is green (`121 passed`, `ruff check .`, and
  `mypy custom_components tests`).

## Procedural instructions for future agents

1. **Read `0_index.md` first** (this file) to understand the roadmap and current progress.
2. Identify the **first incomplete plan whose dependencies are all ✅ Complete**.
3. **Read that plan completely** before modifying any code.
4. Perform any **additional verification/research the plan requires**. Re-read the linked
   official documentation when the plan touches version-sensitive APIs — treat these
   planning docs as a starting point, not permanently authoritative. HA APIs change every
   monthly release; verify against the current docs before relying on an API.
5. **Implement only the scope of that plan.** Do not pull work forward from later plans.
6. Run the **tests / validation specified by the plan** (and keep the whole integration
   loadable by HA at the end of the phase).
7. **Do not silently expand scope.** If you discover new required work, create or update a
   later plan file describing it instead of doing it inline.
8. When finished, **update the plan's own `status` front matter and this master table.**
9. Record **blockers, unknowns, or architectural discoveries** in the relevant plan's
   "Open questions / discoveries" area and, if they affect ordering, in this index.
10. **Keep the repository in a working state after each completed phase** — HA must be able
    to load the integration without errors after every plan (except where a plan explicitly
    documents an intermediate non-loadable state, which should be avoided).

## Verified corrections to the source PRD (authoritative)

These were validated against current (2026) official documentation and **override** the
PRD where they conflict. Each downstream plan restates the ones relevant to it.

- **OptionsFlow:** Do **not** define `__init__(self, config_entry)` that assigns
  `self.config_entry`. Since HA 2024.11 it is deprecated and it **breaks in HA 2025.12+**
  (`config_entry` is a read-only property injected by the base class). Access it via
  `self.config_entry`. Ref: developers.home-assistant.io/blog/2024/11/12/options-flow/
- **Discovery:** Prefer enumerating `hass.config_entries.async_entries("wled")`. Each WLED
  entry stores the host at `entry.data[CONF_HOST]` and identity at `entry.unique_id`
  (normalized **lowercase MAC, no separators**), title at `entry.title`. This replaces the
  PRD's fragile `/states` sensor scan. Ref: home-assistant/core `components/wled`.
- **Device registry:** Devices are restricted to a single config entry (2026.07). Use
  `DeviceRegistry.async_get_device_by_identifier(...)` /
  `async_get_device_by_connection(...)` scoped to a config entry id; avoid the deprecated
  `DeviceEntry.config_entries` accessor. Ref:
  developers.home-assistant.io/blog/2026/07/21/device-registry-single-config-entry/
- **manifest.json:** HACS requires `issue_tracker` in addition to
  `domain/name/codeowners/documentation/version`. The PRD's manifest omits it.
- **Translations:** Custom integrations must **manually** ship a flat `translations/en.json`
  with every key. `strings.json` is an authoring source only and is **not** processed at
  runtime for custom integrations. Ref:
  developers.home-assistant.io/docs/internationalization/custom_integration
- **Branding:** HA brand icons/logos live in the `home-assistant/brands` repo (submitted via
  PR), not inside this repository. A logo in-repo is only for the README. HACS default
  listing requires the brands PR to be merged.
- **WLED restore surface:** `POST /json/cfg` accepts partial config objects. Preset restore
  is performed by uploading `presets.json` to the WLED `/edit` filesystem endpoint
  (multipart). This upload path is **version-sensitive and must be integration-tested**;
  passwords are never present in WLED backups. Ref: kno.wled.ge json-api + presets/settings.
- **WLED sequencing:** Serialize all write operations per device (per-device `asyncio.Lock`).
