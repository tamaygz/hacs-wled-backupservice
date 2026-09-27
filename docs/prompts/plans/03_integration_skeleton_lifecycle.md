---
goal: Implement the integration lifecycle, typed runtime_data, and manager wiring so HA can load/unload the entry
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Planned'
tags: [lifecycle, runtime_data, setup]
---

# 03 — Integration skeleton & lifecycle

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Objective

Provide `async_setup`, `async_setup_entry`, `async_unload_entry`, and (empty) service
registration hook so a single config entry loads and unloads cleanly, with the
`WLEDBackupManager` attached to typed `entry.runtime_data`.

## Scope

In scope: `__init__.py` lifecycle, typed `ConfigEntry`, a minimal `manager.py` shell,
config-entry migration hook, service registration call site (empty). Out of scope: config
flow (04), discovery/client/storage bodies (05–07), real services (10).

## Prerequisites / dependencies

- Plan **02** complete (`const`, `exceptions`).

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/__init__.py
custom_components/wled_backupservice/manager.py      # shell class + typed alias
custom_components/wled_backupservice/services.py     # async_register_services(hass) — empty stub returning None
```

## Detailed implementation tasks

1. Define the typed config entry alias in `manager.py` (or a `types.py`):
   ```python
   type WLEDBackupConfigEntry = ConfigEntry[WLEDBackupManager]
   ```
2. `manager.py`: create `WLEDBackupManager` with `__init__(self, hass, entry)` storing
   `hass`, `entry`, and placeholders for the discovery adapter, client factory, storage,
   retention, per-device locks (`dict[str, asyncio.Lock]`), and scheduler unsub. Add
   `async_setup()` / `async_shutdown()` methods (no-ops for now beyond lock/dict init).
   Public methods (`async_backup_device`, `async_backup_all`, `async_restore`,
   `async_list_backups`, `async_delete_backup`, `async_prune`, `async_discover_devices`)
   are declared here but implemented by later plans — stub them to raise
   `NotImplementedError` so imports resolve.
3. `__init__.py`:
   - `async_setup(hass, config)`: call `services.async_register_services(hass)` so actions
     register **independently of config entries** (per HA action-setup rule). Return `True`.
   - `async_setup_entry(hass, entry)`:
     - Construct `WLEDBackupManager(hass, entry)`, `await manager.async_setup()`.
     - Assign `entry.runtime_data = manager`.
     - Register `entry.async_on_unload(entry.add_update_listener(_async_update_listener))`
       so options changes reload the entry (the scheduler in plan 12 reacts to this).
     - Return `True`.
   - `async_unload_entry(hass, entry)`: `await entry.runtime_data.async_shutdown()`;
     return `True`. (No platforms are forwarded — this is a service integration.)
   - `async_migrate_entry(hass, entry)`: present and returning `True` for `VERSION = 1`
     (migration logic added only when the schema changes; see PRD §30).
   - `_async_update_listener(hass, entry)`: `await hass.config_entries.async_reload(entry.entry_id)`.
4. `services.py`: `async def async_register_services(hass) -> None:` empty for now; plan 10
   fills it. It must be idempotent (guard against duplicate registration across reloads).

## API / framework requirements

- `ConfigEntry[...]` generic + `entry.runtime_data` (typed runtime storage). Ref: HA
  `runtime_data` guidance.
- `entry.add_update_listener` + `entry.async_on_unload` for reload-on-options-change.
- Service registration must occur in `async_setup` (not `async_setup_entry`).

## Important technical decisions

- `WLEDBackupManager` is the single composition root owning discovery/client/storage/
  retention/locks/scheduler — nothing goes into `__init__.py` beyond lifecycle glue
  (PRD §12 anti-pattern warning).
- No entity platforms in v1 (optional diagnostic entities deferred; PRD §17).
- Services register once globally and stay registered even with zero entries.

## Edge cases

- Reload while a backup/scheduler cycle is running: `async_shutdown()` must cancel the
  scheduler unsub and not leave dangling tasks. Coordinate with plan 12.
- Second config entry attempt: blocked by `single_config_entry` (config flow, plan 04) —
  but `async_setup_entry` should still be robust to being called for the single entry.

## Security / safety considerations

- No secrets handled here. Ensure `async_shutdown` cannot raise and block unload.

## Testing requirements

- Test: setting up a `MockConfigEntry` loads the entry (`state == LOADED`) and
  `entry.runtime_data` is a `WLEDBackupManager`.
- Test: unloading the entry succeeds and calls `async_shutdown`.
- Test: `async_register_services` is invoked from `async_setup` and is idempotent across a
  reload (no duplicate-registration error).
- Test: options update triggers `async_reload` via the update listener.

## Acceptance criteria

- [ ] Single config entry loads and unloads without error.
- [ ] `entry.runtime_data` holds the manager (typed).
- [ ] Services register from `async_setup` and survive entry unload.
- [ ] Migration hook present for `VERSION = 1`.

## Definition of done

HA loads and unloads the integration cleanly with an empty-but-wired manager; later plans
fill manager methods and the service registry without touching lifecycle glue.

## References

- runtime_data: https://developers.home-assistant.io/docs/config_entries_index/#runtime-data
- action-setup rule: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/action-setup/
- Config entry lifecycle: https://developers.home-assistant.io/docs/config_entries_index/
- PRD §11 (service registration), §12 (manager), §30 (migration).
