---
goal: Master execution index for the WLED Backup Service HACS integration implementation
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Planned'
tags: [index, roadmap, home-assistant, hacs, wled]
---

# 0 — Master Execution Index

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

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
| 01 | [Repository bootstrap & tooling](01_repository_bootstrap.md)                       | 🔴 Blocked    | —          | Scaffold is in place; repo-local venv and static checks pass, but `pytest-homeassistant-custom-component` blocks event-loop setup on Windows during the smoke test |
| 02 | [Manifest, HACS metadata, branding, foundations](02_manifest_hacs_foundations.md) | ⬜ Not started | 01         | `manifest.json`, `hacs.json`, brands, `const.py`, `exceptions.py` |
| 03 | [Integration skeleton & lifecycle](03_integration_skeleton_lifecycle.md)          | ⬜ Not started | 02         | `__init__.py`, typed `runtime_data`, manager stub, entry loads/unloads |
| 04 | [Config flow & options flow](04_config_options_flow.md)                            | ⬜ Not started | 03         | Single-instance config flow + full options flow + schema |
| 05 | [WLED discovery adapter](05_wled_discovery.md)                                     | ⬜ Not started | 03         | Discover via `wled` config entries + device registry |
| 06 | [Async WLED client](06_wled_client.md)                                             | ⬜ Not started | 02         | `info`/`cfg`/`presets`/`state` GET + `cfg` POST + `/edit` upload |
| 07 | [Storage service](07_storage_service.md)                                           | ⬜ Not started | 02         | Path validation, atomic writes, manifest + sha256 |
| 08 | [Backup engine](08_backup_engine.md)                                               | ⬜ Not started | 05,06,07   | `async_backup_device`, `async_backup_all` |
| 09 | [Retention policy](09_retention.md)                                                | ⬜ Not started | 07,08      | Count + age retention, safe pruning |
| 10 | [Services / actions registration](10_services_actions.md)                          | ⬜ Not started | 08,09      | `async_setup` registration, `services.yaml`, response data, targeting |
| 11 | [Restore engine](11_restore_engine.md)                                             | ⬜ Not started | 06,07,08   | cfg + presets restore, safety backup, per-device lock, verify |
| 12 | [Scheduler](12_scheduler.md)                                                       | ⬜ Not started | 08,09      | `async_track_time_interval` / daily time, no-overlap guard |
| 13 | [Diagnostics](13_diagnostics.md)                                                   | ⬜ Not started | 03,08      | `diagnostics.py`, redaction |
| 14 | [Translations & UI polish](14_translations_ui.md)                                  | ⬜ Not started | 04,10,11   | `translations/en.json`, `strings.json`, `data_description` |
| 15 | [Testing & coverage gate](15_testing_coverage.md)                                  | ⬜ Not started | all above  | Cross-cutting fixtures, coverage >95%, gap-filling |
| 16 | [CI, Hassfest & HACS validation](16_ci_validation.md)                             | ⬜ Not started | 15         | GitHub Actions: hassfest, HACS action, tests |
| 17 | [Documentation & release](17_documentation_release.md)                            | ⬜ Not started | 16         | README, info.md, quality_scale, GitHub release |

Statuses: ⬜ Not started · 🟡 In progress · ✅ Complete · 🔴 Blocked

## Current blocker

- Plan 01 is blocked on the Windows bootstrap test path. The repo-local `.venv-py311`
  environment is working, and `ruff`/`mypy` pass, but the required HA pytest plugin stack
  fails before the smoke test body runs because sockets are blocked during event-loop
  creation. Resolve that test-harness issue before moving to plan 02.

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
