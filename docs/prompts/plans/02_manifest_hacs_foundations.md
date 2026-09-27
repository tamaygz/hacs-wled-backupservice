---
goal: Define integration manifest, HACS metadata, branding, and shared foundations (const + exceptions)
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [manifest, hacs, const, exceptions, branding]
---

# 02 — Manifest, HACS metadata, branding & foundations

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Make the repository a recognizable HACS integration and provide the shared, dependency-free
foundation modules (`const.py`, `exceptions.py`) that nearly every later plan imports.

## Scope

In scope: `manifest.json`, `hacs.json`, `const.py`, `exceptions.py`, branding plan/assets.
Out of scope: integration runtime logic (03+), CI validation (16).

## Prerequisites / dependencies

- Plan **01** complete (repo skeleton + package folder exists).

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/manifest.json
custom_components/wled_backupservice/const.py
custom_components/wled_backupservice/exceptions.py
hacs.json
brand/README.md            # note pointing to home-assistant/brands submission
```

## Detailed implementation tasks

1. **`manifest.json`** — start from PRD §20 and **add `issue_tracker`** (HACS-required):
   ```json
   {
     "domain": "wled_backupservice",
     "name": "WLED Backup Service",
    "codeowners": ["@tamaygz"],
     "config_flow": true,
    "documentation": "https://github.com/tamaygz/hacs-wled-backupservice",
    "issue_tracker": "https://github.com/tamaygz/hacs-wled-backupservice/issues",
     "integration_type": "service",
     "iot_class": "local_polling",
     "single_config_entry": true,
     "version": "1.0.0",
     "requirements": []
   }
   ```
   - Keep `requirements` empty unless plan 06 concludes a dependency is required (default:
     no third-party deps; use stdlib + HA-provided `aiohttp`).
   - Verify every key against the **current** Integration Manifest doc before release;
     `integration_type: "service"` and `single_config_entry: true` are both current keys.
2. **`hacs.json`** (repo root):
   ```json
   { "name": "WLED Backup Service", "homeassistant": "2025.12.0", "content_in_root": false }
   ```
   - Choose the **minimum HA version** based on APIs actually used. Because the options
     flow relies on the post-2024.11 auto-injected `config_entry` and this project targets
     the read-only-property world, set the floor at **2025.12.0** (the release where the
     old setter is removed) unless a later plan needs a higher floor. Record the final
     decision and reconcile with the `homeassistant` pin in `pyproject.toml`.
3. **`const.py`**: domain, name, logger, config/option keys and defaults, storage roots,
   schema versions. Suggested contents:
   - `DOMAIN = "wled_backupservice"`, `LOGGER = logging.getLogger(__package__)`.
   - Option keys: `CONF_SCHEDULE_ENABLED`, `CONF_INTERVAL`, `CONF_INTERVAL_UNIT`,
     `CONF_DAILY_TIME`, `CONF_STORAGE_ROOT`, `CONF_SUBDIR`, `CONF_INCLUDE_PRESETS`,
     `CONF_INCLUDE_STATE`, `CONF_CREATE_ARCHIVE`, `CONF_RETENTION_COUNT`,
     `CONF_RETENTION_DAYS`, `CONF_BACKUP_BEFORE_RESTORE`, `CONF_VERIFY_AFTER_RESTORE`,
     `CONF_REBOOT_AFTER_RESTORE`.
   - Defaults per PRD §6/§14: `DEFAULT_INTERVAL = 24`, `DEFAULT_INTERVAL_UNIT = "hours"`,
     `DEFAULT_RETENTION_COUNT = 30`, `DEFAULT_INCLUDE_PRESETS = True`,
     `DEFAULT_INCLUDE_STATE = False`, `DEFAULT_BACKUP_BEFORE_RESTORE = True`.
   - `STORAGE_ROOTS = {"share": "/share", "media": "/media", "backup": "/backup", "config": "/config"}`.
     (Resolve `/config` via `hass.config.path()` at runtime rather than hardcoding — leave
     a note; storage plan 07 owns the resolver.)
   - `BACKUP_SCHEMA_VERSION = 1`, `MANIFEST_FILENAME = "manifest.json"`,
     `CFG_FILENAME = "cfg.json"`, `PRESETS_FILENAME = "presets.json"`,
     `STATE_FILENAME = "state.json"`, `INFO_FILENAME = "info.json"`.
   - WLED source integration domain constant: `WLED_DOMAIN = "wled"`.
4. **`exceptions.py`**: define the hierarchy from PRD §16, all subclassing a base:
   `WLEDBackupError(HomeAssistantError)`, and `WLEDConnectionError`,
   `WLEDValidationError`, `WLEDBackupNotFoundError`, `WLEDRestoreError`,
   `WLEDStorageError`, `WLEDDiscoveryError`. Subclass `HomeAssistantError` so raising them
   from services yields user-facing HA errors; support `translation_domain`/
   `translation_key` kwargs (they are accepted by `HomeAssistantError`).
5. **Branding**: create `brand/README.md` documenting that the actual HA icon/logo must be
   submitted to the `home-assistant/brands` repo (`custom_integrations/wled_backupservice/`)
   via PR, and that this must be merged before HACS default listing. Optionally keep a
   README logo image, but do **not** rely on an in-repo `brand/icon.png` being used by HA.

## API / framework requirements

- `homeassistant.exceptions.HomeAssistantError` supports `translation_domain`,
  `translation_key`, and `translation_placeholders` kwargs.
- Manifest schema: current keys validated by `hassfest` (plan 16).

## Important technical decisions

- **No third-party runtime dependencies** by default. Reconsider only in plan 06.
- Base all custom exceptions on `HomeAssistantError` so service failures surface cleanly.
- HA minimum version floor is a **release-blocking decision**; keep it as low as the used
  APIs allow but no lower than 2025.12 given the options-flow API assumption.

## Edge cases

- `/config` is not a fixed absolute path in all installs — must be resolved via
  `hass.config.path()`; do not hardcode `/config` in storage logic.
- `single_config_entry: true` means the config flow must abort a second instance (plan 04).

## Security / safety considerations

- Do not add network-capable third-party deps casually (supply-chain surface).
- `documentation`/`issue_tracker` URLs must point to the real repo.

## Testing requirements

- A test asserts `manifest.json` parses and contains the HACS-required keys
  (`domain`, `name`, `codeowners`, `documentation`, `issue_tracker`, `version`).
- A test asserts `hacs.json` parses and contains `name` + `homeassistant`.
- A test imports `const` and `exceptions` and asserts each exception subclasses
  `HomeAssistantError`.

## Acceptance criteria

- [x] `manifest.json` includes `issue_tracker` and `single_config_entry: true`.
- [x] `hacs.json` present at repo root with a justified `homeassistant` floor.
- [x] `const.py` exposes all option keys/defaults referenced by later plans.
- [x] `exceptions.py` hierarchy present, all subclassing `HomeAssistantError`.
- [x] Branding submission process documented.

## Definition of done

HACS/hassfest can recognize the integration's metadata (full validation in plan 16), and
downstream plans can `from .const import ...` / `from .exceptions import ...`.

## Open questions / discoveries

- 2026-09-27: The repository now includes `brand/icon.png` as a temporary local HACS brand
  asset placeholder so the repo structure matches HACS integration requirements. Replace it
  with the final branded icon before release.
- 2026-09-27: `hacs.json` now declares a 2025.12.0 HA floor, while local development is
  still pinned to Home Assistant 2024.3.3 in `pyproject.toml` because the current repo
  bootstrap venv is Python 3.11. Reconcile the local dev/test stack with the published HA
  floor in a later environment upgrade pass before release.

## References

- Integration manifest: https://developers.home-assistant.io/docs/creating_integration_manifest/
- HACS integration requirements: https://hacs.xyz/docs/publish/integration/
- HA brands repo: https://github.com/home-assistant/brands
- `HomeAssistantError` translations: https://developers.home-assistant.io/docs/core/platform/raising_exceptions/
- PRD §20, §21, §16, §2 (HACS requirements).
