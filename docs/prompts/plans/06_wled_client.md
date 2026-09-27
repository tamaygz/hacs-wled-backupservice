---
goal: Implement an async WLED HTTP client for reading and restoring config, presets, state, and info
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Planned'
tags: [http, aiohttp, wled-api]
---

# 06 — Async WLED client

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Objective

Provide a non-blocking `WLEDClient` using HA's shared aiohttp session to read `/json/info`,
`/json/cfg`, `/presets.json`, `/json/state` and to restore config (`POST /json/cfg`) and
presets (upload via `/edit`), with bounded timeouts and precise error typing.

## Scope

In scope: `wled_client.py`, typed info model, error mapping. Out of scope: deciding what to
back up (08) or restore sequencing/safety (11).

## Prerequisites / dependencies

- Plan **02** complete (const, exceptions). Independent of discovery/storage.

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/wled_client.py
```

## Detailed implementation tasks

1. `WLEDClient(host, session, *, timeout=...)` where `session = async_get_clientsession(hass)`
   (shared HA session; never create per-call sessions, never use `requests`).
   Normalize `host` into a base URL (`http://<host>`), tolerating an already-scheme'd host.
2. Read methods (GET, bounded `aiohttp.ClientTimeout`):
   - `async_get_info() -> WLEDInfo` — GET `/json/info`; parse `brand`, `mac` (→ `mac_address`),
     `ver`, `arch`, `name`, `vid`. Validate JSON + presence of identity fields.
   - `async_get_config() -> dict` — GET `/json/cfg` (raw JSON dict, stored as received).
   - `async_get_presets_raw() -> bytes` — GET `/presets.json` (raw bytes; **may be large** —
     read fully but guard with a max-size limit; stream-read where practical).
   - `async_get_state() -> dict` — GET `/json/state`.
3. Restore/write methods (serialized by caller, plan 11):
   - `async_set_config(config: dict) -> None` — `POST /json/cfg` with the config object
     (WLED accepts partial/whole config objects). Check for a success response; WLED returns
     a verbose/ack payload — treat non-2xx or an error body as failure.
   - `async_upload_presets(payload: bytes) -> None` — **version-sensitive**. WLED's UI
     restores presets by uploading `presets.json` to the ESPAsyncWebServer **`/edit`
     filesystem endpoint** (multipart form, filename `presets.json`). Implement this as the
     primary mechanism (multipart `aiohttp.FormData` POST to `/edit`). Document that OTA
     lock must be off. This path **must be integration-tested** against real firmware before
     claiming success (see plan 11 + PRD §10). Provide a clear capability flag so the manager
     can surface "presets restore unavailable/unverified" rather than silently succeeding.
   - `async_set_state(state: dict) -> None` — `POST /json/state` (optional; for completeness).
   - `async_reboot() -> None` — request reboot after config restore where appropriate
     (e.g. `POST /json/state {"rb":true}` if supported by the target firmware; verify).
4. Error mapping — translate transport/HTTP failures into the plan-02 exceptions:
   - connection refused / DNS / OSError → `WLEDConnectionError`.
   - timeout (`asyncio.TimeoutError`) → `WLEDConnectionError` (timeout subtype/message).
   - non-2xx → `WLEDConnectionError` with status.
   - malformed JSON / unexpected content-type → `WLEDValidationError`.
   - payload exceeds max size → `WLEDValidationError`.
5. `async_close()` — no-op for the shared session (documented), present for symmetry.
6. Never log full `cfg`/`presets` payloads or secrets; log method + host + status only.

## API / framework requirements

- `homeassistant.helpers.aiohttp_client.async_get_clientsession`.
- WLED JSON API (verified 2026-09):
  - `GET /json/info` → `brand`, `mac`, `ver`, `arch`, `name`.
  - `GET /json/cfg`, `POST /json/cfg` (accepts whole/partial config object).
  - `GET /presets.json` (filesystem file; may be large).
  - `GET/POST /json/state`.
  - Preset upload via `/edit` multipart (ESPAsyncWebServer).
- WLED guidance: sequence large-data write calls; enforced by caller (plan 11).

## Important technical decisions

- **Do not** add the `python-wled` dependency by default: it targets state/info, not raw
  `cfg`/`presets` file transfer, so it does not cover the backup surface. Implement a
  minimal purpose-built client with stdlib + `aiohttp`. (Reconsider only if a maintained
  dependency clearly covers cfg + presets file I/O; record the decision in `manifest.json`.)
- Preset upload endpoint (`/edit`) is the **known unknown** — isolate it and gate it behind
  an integration-tested capability flag.
- Bounded per-request timeouts (e.g. 10s info/cfg/state, larger for presets upload).

## Edge cases (PRD §22 HTTP suite)

- success; timeout; connection refused; HTTP 404; HTTP 401/403 (OTA lock / auth) —
  surface a clear error; invalid JSON; empty preset response; very large preset response;
  unexpected content type.

## Security / safety considerations

- No secrets in logs. WLED backups exclude passwords (firmware behavior) — do not attempt
  to extract them.
- Enforce a max response size for presets to avoid unbounded memory.
- Only talk to hosts derived from discovered `wled` entries (no arbitrary host from service
  input for GETs; restore targets are resolved devices, plan 11).

## Testing requirements

- Mock aiohttp (`aioresponses`/`aioclient_mock`) — never hit the network.
- Cover every edge case above for each method.
- Assert error-type mapping (connection vs validation).
- Assert `async_upload_presets` builds a correct multipart request to `/edit`.

## Acceptance criteria

- [ ] All read methods parse and validate; all raise typed errors on failure.
- [ ] `async_set_config` posts to `/json/cfg` and detects failure.
- [ ] `async_upload_presets` targets `/edit` multipart and is capability-gated + tested.
- [ ] No blocking I/O; shared HA session used.
- [ ] >95% coverage for `wled_client.py`.

## Definition of done

The client can read all backup artifacts and perform config/preset restore against mocked
WLED responses, with precise error typing and no event-loop blocking.

## References

- WLED JSON API: https://kno.wled.ge/interfaces/json-api/
- WLED presets (backup/restore via /edit): https://kno.wled.ge/features/presets/
- WLED settings backup/restore (passwords not backed up): https://kno.wled.ge/features/settings/
- HA aiohttp client: https://developers.home-assistant.io/docs/api_lib_auth/ (session usage) and `aiohttp_client` helper.
- PRD §9 (client), §10 (restore), §24 (firmware), §33 (cautions).

## Open questions / discoveries

- Confirm the exact `/edit` multipart field name and whether newer firmware exposes a JSON
  API preset-file upload. Verify against the firmware versions targeted in plan 17 before
  release; if `/edit` is unavailable/locked, mark preset restore unsupported for that device.
