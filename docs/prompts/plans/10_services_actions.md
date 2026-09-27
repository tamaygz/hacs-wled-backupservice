---
goal: Register all HA Actions with services.yaml, response data, and device targeting
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [services, actions, api]
---

# 10 — Services / actions registration

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Expose the manager's capabilities as HA Actions registered in `async_setup`, with a
complete `services.yaml`, structured response data where useful, and safe device targeting.

## Scope

In scope: `services.py` (fill the stub from plan 03), `services.yaml`, schema validation,
target resolution, response data. Out of scope: manager internals (08/09/11), scheduler (12).

## Prerequisites / dependencies

- Plans **08** (backup), **09** (retention) complete. `restore` handler wiring finalized in
  plan **11** (register the action here but its handler may call plan-11 manager code — keep
  ordering: implement `restore` action body after 11, or land 11 first).

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/services.py
custom_components/wled_backupservice/services.yaml
```

## Detailed implementation tasks

1. `async_register_services(hass)` (idempotent): register each action once. Guard with a
   `hass.services.has_service(DOMAIN, name)` check so reloads don't double-register.
   Handlers must locate the (single) config entry / manager via
   `hass.config_entries.async_entries(DOMAIN)` → `entry.runtime_data`, and raise a clear
   `HomeAssistantError` when no entry is loaded (actions stay registered even with zero
   entries — that behavior is required and tested).
2. Actions (PRD §11):
   - **`backup`** — target `device_id`(s); options `include_presets`, `include_state`,
     `label`. `SupportsResponse.OPTIONAL`; returns per-device `BackupResult`s.
   - **`backup_all`** — no target; `SupportsResponse.OPTIONAL`; returns all results.
   - **`restore`** — required: target device + `backup_id`; options `backup_before_restore`,
     `restore_config`, `restore_presets`, `verify_after_restore`, `reboot_after_restore`.
     Destructive. `SupportsResponse.OPTIONAL`. Body delegates to plan-11 `async_restore`.
   - **`list_backups`** — optional device, optional `limit`, optional include metadata.
     `SupportsResponse.ONLY`; returns backups (id/device/timestamp/files/sizes/firmware/
     integrity).
   - **`delete_backup`** — required `backup_id`. `SupportsResponse.OPTIONAL`.
   - **`prune`** — optional device, `dry_run`. `SupportsResponse.OPTIONAL`.
   - **`discover`** — force discovery refresh; `SupportsResponse.OPTIONAL` returns device list.
3. **Target resolution**: for device-targeted actions, use
   `discovery.async_resolve_target_devices(hass, call)` (plan 05) to map HA `device_id`s to
   `WLEDDevice`s and reject non-WLED devices with a translatable error.
4. **Schema**: `voluptuous` per-action schemas; `backup_id` is an integration-generated
   opaque id (never an arbitrary path). Validate types; raise `WLEDValidationError` /
   `ServiceValidationError` for bad input.
5. **`services.yaml`**: full field metadata, selectors (device selector filtered where
   possible), descriptions, and `response` sections. UI text lives in `services.yaml` +
   translations (plan 14).
6. Map raised `WLEDBackup*` errors to user-facing HA errors (they subclass
   `HomeAssistantError`); include `translation_key` where a translated message is desired.

## API / framework requirements

- `hass.services.async_register(DOMAIN, name, handler, schema=..., supports_response=...)`
  with `homeassistant.core.SupportsResponse` (`ONLY`/`OPTIONAL`).
- `ServiceCall`, `ServiceResponse` (JSON-serializable dict return).
- Registration in `async_setup` (action-setup quality rule).
- Device targeting via `ServiceCall` target + device registry.

## Important technical decisions

- Response data returned as JSON-serializable dicts (no dataclasses directly — convert).
- `list_backups` is `SupportsResponse.ONLY` (pure read). Mutating actions use `OPTIONAL`.
- `restore`/`delete_backup` accept only integration-generated `backup_id`s resolved inside
  the configured root (no arbitrary paths) — enforced in storage (plan 07).

## Edge cases (PRD §22 service suite)

- Valid invocation; selector resolution; **no config entry loaded** (clear error, action
  still registered); no discovered device; device offline; response data returned; error
  propagation to the UI.
- `restore` without required `backup_id` or device → validation error.
- Non-WLED `device_id` targeted → rejected.

## Security / safety considerations

- Never accept arbitrary filesystem paths from service data (PRD §11, §23).
- Reject restore/backup against non-WLED devices.
- Destructive actions (`restore`, `delete_backup`) clearly documented in `services.yaml`.

## Testing requirements

- Every action: valid call + error paths.
- Actions registered from `async_setup` and callable with **zero** config entries loaded
  (raising the documented error), proving registration independence.
- Response data shape for `backup`/`backup_all`/`list_backups`/`discover`.
- Target resolution + non-WLED rejection.

## Acceptance criteria

- [x] All seven actions registered from `async_setup`, idempotent across reloads.
- [x] `services.yaml` complete with fields, selectors, descriptions, response.
- [x] Response data works for read/return actions.
- [x] Arbitrary paths impossible; non-WLED targets rejected.
- [x] >95% coverage for `services.py`.

## Definition of done

All actions are usable from the HA Actions UI with correct schemas, response data, safe
targeting, and meaningful errors; registration survives entry unload.

## Validation completed

- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy custom_components tests`

## Open questions / discoveries

- Service registration remains independent of loaded config entries: actions are registered
  from `async_setup`, stay available when no entry is loaded, and raise explicit
  `HomeAssistantError` messages until runtime state exists.
- `restore` is registered now, but its handler intentionally raises a clear
  "not available until the restore engine is implemented" error until plan 11 lands.
- Response payloads are fully JSON-serialized in `services.py`; dataclasses from backup,
  retention, discovery, and storage are converted before returning to Home Assistant.
- Full-suite validation after plan-10 landing is green (`97 passed`, total coverage 93%),
  while the existing `pytest-asyncio` custom `event_loop` deprecation warning remains an
  unchanged baseline unrelated to service behavior.

## References

- Integration service actions: https://developers.home-assistant.io/docs/dev_101_services/
- action-setup rule: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/action-setup/
- Responding services (response data): https://www.home-assistant.io/blog/2023/07/05/release-20237/#responding-services-actions-that-give-you-data-back
- PRD §11 (actions), §28 (targeting), §23 (security).
