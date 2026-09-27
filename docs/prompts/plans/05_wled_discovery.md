---
goal: Discover WLED devices from Home Assistant's native wled integration and expose a stable device model
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Planned'
tags: [discovery, device-registry, wled]
---

# 05 — WLED discovery adapter

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Objective

Provide `async_discover_wled_devices(hass) -> list[WLEDDevice]` that enumerates WLED devices
already configured in HA's native `wled` integration, deriving host + stable identity, with
compatibility isolated behind this adapter.

## Scope

In scope: `discovery.py`, `WLEDDevice` dataclass, target-resolution helper for services.
Out of scope: verifying devices over HTTP (that is the client's `/json/info`, plan 06,
though discovery may call it optionally), backups (08).

## Prerequisites / dependencies

- Plan **03** complete (lifecycle, const). Independent of 04/06/07.

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/discovery.py
```

## Detailed implementation tasks

1. Define the frozen dataclass (PRD §8):
   ```python
   @dataclass(frozen=True)
   class WLEDDevice:
       device_id: str          # our stable id: normalized MAC, else host
       name: str               # entry.title / device name
       host: str               # from wled entry.data[CONF_HOST]
       mac: str | None         # normalized lowercase, no separators
       ha_device_id: str | None
       ha_config_entry_id: str | None
       firmware_version: str | None
   ```
2. **Primary discovery source** (verified against current core `components/wled`):
   - `entries = hass.config_entries.async_entries(WLED_DOMAIN)` (`WLED_DOMAIN = "wled"`).
   - For each `entry`:
     - `host = entry.data[CONF_HOST]` (import `CONF_HOST` from `homeassistant.const`).
     - `mac = entry.unique_id` — the WLED integration normalizes this to lowercase MAC
       without separators (its `normalize_mac_address`). Treat it as the identity.
     - `name = entry.title`.
     - Look up the HA device via the **device registry scoped to the entry**:
       `dr.async_get(hass)` then `async_get_device_by_connection((CONNECTION_NETWORK_MAC, format_mac(mac)), entry.entry_id)`
       or `async_get_device_by_identifier((WLED_DOMAIN, mac), entry.entry_id)`. Use the
       new single-entry-scoped methods; **do not** use deprecated `DeviceEntry.config_entries`.
       Derive `ha_device_id`, and `firmware_version` from `device.sw_version` when available.
3. **Identity priority** (PRD §8): (1) WLED deviceId if exposed, (2) normalized MAC (this is
   `entry.unique_id`), (3) HA device/config-entry id, (4) host as last resort. In practice
   `entry.unique_id` (MAC) is authoritative for current firmware; keep the fallback chain.
4. **`device_id`** (our stable directory identity): use `mac` when present, else a sanitized
   host. Never use the friendly name as identity.
5. Provide `async_resolve_target_devices(hass, call) -> list[WLEDDevice]` (PRD §28):
   resolve a service `device_id` target (HA device registry id) back to a `WLEDDevice` by
   matching the device's owning config entry to the `wled` domain; **reject non-WLED
   devices** with a clear `WLEDValidationError`.
6. Isolate all registry/entry access in this module so a future HA change only touches
   `discovery.py`; add a module docstring noting the version-sensitive assumptions and the
   date verified.

## API / framework requirements

- `hass.config_entries.async_entries(domain)`.
- `homeassistant.helpers.device_registry` (`async_get`, `async_get_device_by_connection`,
  `async_get_device_by_identifier`, `format_mac`, `CONNECTION_NETWORK_MAC`).
- `homeassistant.const.CONF_HOST`.
- WLED entry facts (verified 2026-09): `entry.data[CONF_HOST]`, `entry.unique_id` =
  normalized MAC, `entry.title` = name, `entry.runtime_data` = WLED coordinator.

## Important technical decisions

- **Do not** reproduce the reference add-on's global `sensor.*` scan (fragile; PRD §3.3,
  §33). The `wled` config entries are the source of truth.
- Do not depend on the WLED **IP sensor** entity being enabled.
- Do not depend on `entry.runtime_data` internals of the `wled` integration (private);
  prefer `entry.data`/registry. If host is ever missing from `data`, degrade gracefully and
  log a warning rather than reaching into another integration's runtime object.

## Edge cases (PRD §22 discovery suite)

- Zero WLED devices → return `[]`.
- One / multiple devices.
- Duplicate host (two entries, same host) → still distinct by MAC.
- Missing IP/host in `entry.data` → skip with warning (do not crash).
- Unavailable WLED (entry present, device offline) → still discoverable (verification is
  separate).
- Identity based on MAC / device id.
- Friendly-name collision → directory identity must remain unique via MAC suffix.

## Security / safety considerations

- No LAN scanning. Only inspect known `wled` entries.
- Do not log full config-entry data (may contain host/network info at DEBUG only).

## Testing requirements

- Mock `wled` config entries + device registry; assert correct `WLEDDevice` mapping for the
  edge cases above.
- Test `async_resolve_target_devices` rejects a non-WLED `device_id`.
- Test name-collision produces unique `device_id`.

## Acceptance criteria

- [ ] Discovers all `wled` entries with host + MAC identity.
- [ ] No dependency on IP sensor or friendly name for identity.
- [ ] Target resolver rejects non-WLED devices.
- [ ] Registry access uses current (non-deprecated) scoped APIs.

## Definition of done

`async_discover_wled_devices` returns a correct, stable device list from the HA `wled`
integration across the tested edge cases, with all HA-version-sensitive logic isolated here.

## References

- Core `components/wled` (`__init__.py`, `coordinator.py`, `const.py`) — verified host in
  `entry.data[CONF_HOST]`, MAC in `entry.unique_id`.
- Device registry single-entry scoping: https://developers.home-assistant.io/blog/2026/07/21/device-registry-single-config-entry/
- Device registry helpers: https://developers.home-assistant.io/docs/device_registry_index/
- PRD §8 (discovery), §28 (targeting), §33 (cautions).
