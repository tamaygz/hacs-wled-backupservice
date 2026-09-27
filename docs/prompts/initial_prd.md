# HACS WLED Backup Service — PRD & Implementation Plan

## 1. Project definition

**Project:** `hacs-wled-backupservice`  
**GitHub owner:** `@tamaygz`  
**Integration domain:** `wled_backupservice`  
**Display name:** `WLED Backup Service`  
**Distribution:** Home Assistant custom integration via HACS  
**Scope:** One Home Assistant config entry that provides scheduled and on-demand backup/restore/management services for WLED devices already known to Home Assistant.

### Product goal

Create a native, UI-first HACS integration that protects WLED configurations without requiring an add-on, Docker container, YAML configuration, manual IP lists, or manual volume mappings.

The user should:

1. Install the integration through HACS.
2. Add **one** integration instance through the Home Assistant UI.
3. Configure backup schedule, destination, retention, and content through the options UI.
4. Let the integration discover WLED devices from Home Assistant's existing WLED integration.
5. Use Home Assistant Actions/services to backup, restore, list, inspect, delete, and optionally prune WLED backups.
6. Never need to configure WLED IP addresses manually for normal operation.

The reference implementation at `pctony/hass_wled_pro_backup` is a useful functional baseline, but its add-on architecture must **not** be copied. Its core behavior is:
- discover WLED candidates through HA state data,
- verify devices with `/json/info`,
- save `/json/cfg`,
- save `/presets.json`,
- organize timestamped backups,
- retain/prune historical backups.

The new implementation should use Home Assistant's native async integration architecture and the currently supported HA config-entry/service patterns.

---

## 2. External references and important findings

### Existing reference implementation

Repository:
`https://github.com/pctony/hass_wled_pro_backup`

The reference project is an HA add-on using:
- `SUPERVISOR_TOKEN`,
- `/data/options.json`,
- a Docker/Alpine image,
- a perpetual Python loop,
- direct filesystem access to `/share`, `/media`, and `/backup`.

Its `backup.py`:
- scans `/states` for sensors whose entity ID contains `ip` or `address`,
- verifies candidates with `GET http://<ip>/json/info`,
- treats `brand == "WLED"` or presence of `name` as evidence,
- retrieves `GET /json/cfg`,
- retrieves `GET /presets.json`,
- creates `Device/YYYY/MM/DD/HHMMSS/`,
- JSON-formats the responses,
- deletes files older than a configured day count.

Those mechanisms are useful as historical behavior, but discovery should be improved substantially in the new integration.

### Home Assistant architecture

Use a Config Flow and a single config entry. Home Assistant documents `single_config_entry` specifically for integrations that support only one instance. The config flow stores connection/setup data in `ConfigEntry.data`; user-adjustable behavior belongs in `ConfigEntry.options`. citeturn214561search0turn214561search2turn214561search10

Use an Options Flow so the user can later change schedule, storage, retention, and backup behavior from the integration UI. citeturn760532search3

Register integration service actions in `async_setup`, not `async_setup_entry`, so the actions remain registered even when there are no loaded config entries. Home Assistant also supports service response data for actions that return structured information such as backup listings/results. citeturn569126search0

Use typed `ConfigEntry.runtime_data` for non-persistent runtime objects such as the manager/coordinator. citeturn826650search7

Custom integrations must ship translation files under `translations/<language>.json`; do not rely on core `strings.json` behavior. citeturn214561search4

The current HA quality-scale baseline calls for service registration, config-flow test coverage, >95% test coverage, common modules, branding, and appropriate UI/configuration behavior. citeturn214561search1turn214561search6

### Current WLED API facts

WLED's current JSON API documents:
- `GET /json` for combined state/info/effects/palettes,
- `GET /json/info` for device information,
- `GET /json/cfg` for the configuration object,
- `POST /json/cfg` for configuration updates,
- `GET /json/state` / `POST /json/state` for runtime light state. citeturn569126search1turn526439search0

WLED documents `/presets.json` as the filesystem file containing presets and explicitly documents downloading that file for backup and uploading it to restore presets. Presets can contain normal lighting state as well as API-command/macro presets. citeturn813438search2turn569126search4

WLED's docs recommend the JSON API for new integrations rather than the older HTTP `/win` API. citeturn813438search1

WLED's `/json/info` exposes stable identity data including MAC address, device ID on newer firmware, firmware version, and IP address; standard WLED builds report `brand: "WLED"`. citeturn526439search0

The WLED documentation says API requests that manipulate large amounts of data should be made sequentially rather than in parallel. The implementation must therefore serialize restore/write operations per device. citeturn526439search0

### HACS requirements

HACS integration repositories require one integration under `custom_components/<domain>/`, a valid `manifest.json`, and branding. GitHub releases are preferred. citeturn826650search0

The repository should contain `hacs.json` at the root. HACS also recommends a public GitHub repository with a description, topics, README, and release process. citeturn826650search5

For eventual inclusion in HACS default repositories, use both Hassfest and the HACS action and publish a GitHub release. citeturn826650search1turn826650search3

### HAOS storage

Home Assistant OS exposes `/config`, `/media`, `/share`, `/backup`, etc. Network storage configured through **Settings → System → Storage → Add network storage** can be mounted for Backup, Media, or Share usage. citeturn648556search0

Therefore:
- support `/share`, `/media`, `/backup`, and `/config` as explicitly documented filesystem roots,
- allow the user to select an approved root + relative subdirectory,
- never allow arbitrary absolute filesystem paths,
- do not introduce a Docker mount configuration requirement.

---

# 3. Product principles

## 3.1 Native Home Assistant experience

Everything important must be accessible through Home Assistant:
- installation via HACS,
- setup via Config Flow,
- settings via Options Flow,
- actions via HA Actions UI,
- device selection via HA device selectors,
- logs via standard HA logging,
- failures surfaced as HA errors,
- translations via integration translations.

## 3.2 One integration instance

The integration manages all WLED devices in the HA installation.

`manifest.json` must use:

```json
"single_config_entry": true
```

Do not create one config entry per WLED device.

## 3.3 WLED-first discovery

The integration should preferentially inspect the existing Home Assistant WLED integration rather than scan arbitrary IP addresses.

Important: do **not** reproduce the reference project's broad `/states` sensor scan as the primary discovery mechanism. That approach is fragile because it depends on entity naming and whether the WLED IP entity is enabled.

The integration should use the Home Assistant device/config/entity registries to identify devices belonging to the `wled` integration and derive their configured host/connection information where available.

If the exact current WLED registry representation changes between HA releases, isolate that logic in a dedicated discovery adapter and write compatibility tests.

Optional fallback behavior may verify a known WLED host with `/json/info`, but arbitrary LAN scanning is out of scope for v1.

## 3.4 Backups must be safe and atomic

Never leave a half-written backup appearing as a valid backup.

Write to a temporary file/directory and atomically rename into place after successful completion.

A restore should:
1. validate the backup,
2. fetch/verify current device identity,
3. optionally create a safety backup before modifying the device,
4. apply changes sequentially,
5. report exactly which portions succeeded/failed.

## 3.5 Do not hide dangerous restore operations

Restoring configuration can modify network/Wi-Fi/MQTT/device behavior and can make a device temporarily inaccessible.

The UI and action descriptions must clearly state that config restore can change connectivity and reboot-related settings.

---

# 4. Supported backup content

## Required v1 content

Each backup represents a WLED device snapshot.

### `manifest.json`

A metadata file generated by this integration:

```json
{
  "schema_version": 1,
  "created_at": "2026-09-27T02:43:00+02:00",
  "integration_version": "1.0.0",
  "device": {
    "name": "Kitchen WLED",
    "host": "192.168.1.50",
    "mac": "aabbccddeeff",
    "device_id": "...",
    "firmware_version": "0.15.x"
  },
  "files": [
    {
      "name": "cfg.json",
      "size": 12345,
      "sha256": "..."
    },
    {
      "name": "presets.json",
      "size": 23456,
      "sha256": "..."
    }
  ]
}
```

Do not rely on directory names alone to identify the device.

### `cfg.json`

Fetched from:

```text
GET /json/cfg
```

Store the JSON payload as received/normalized.

### `presets.json`

Fetched from:

```text
GET /presets.json
```

Because WLED specifically documents this file as the backup/restore representation of presets, keep the raw JSON payload available rather than reconstructing it from the state API. citeturn569126search4

## Optional v1.1/v2 content

Design the code so additional artifacts can be added without changing the storage model:

- current `state.json` from `/json/state`,
- `info.json` from `/json/info`,
- custom palettes if a reliable supported endpoint exists,
- additional filesystem files where WLED explicitly documents a stable API,
- a complete downloadable archive.

Do **not** silently back up security-sensitive data such as passwords or Wi-Fi secrets unless the WLED API explicitly documents that behavior and the product intentionally opts into it.

---

# 5. Storage model

Default destination:

```text
/share/wled_backups/
```

Default per-device layout:

```text
/share/wled_backups/
  Kitchen_WLED/
    2026/
      09/
        27/
          024300/
            manifest.json
            cfg.json
            presets.json
```

Prefer a filesystem-safe stable device directory based on a sanitized display name plus an identity suffix if necessary:

```text
Kitchen_WLED_aabbcc
```

Avoid collisions when two devices have the same HA display name.

### Storage options

The Options Flow must expose:

- **Storage root**
  - `/share`
  - `/media`
  - `/backup`
  - `/config`
- **Backup subdirectory**
  - relative path only
  - normalized and validated
  - prevent `..` traversal
- **Include presets**
  - boolean
- **Include runtime state**
  - boolean, default false
- **Create archive**
  - boolean, optional
- **Retention mode**
  - by number of backups
  - by age
  - optionally both
- **Maximum backups per device**
- **Maximum age in days**

User wording should make clear that `/backup` refers to an HA backup-storage mount and not necessarily a network mount.

---

# 6. Backup scheduling

The schedule must be configurable in the Options Flow.

## Recommended v1 controls

- Enable scheduled backups: boolean
- Frequency: numeric + unit
- Unit:
  - minutes
  - hours
  - days
- Optional exact time when unit = days

Recommended defaults:

```text
enabled: true
interval: 24 hours
retention_count: 30
include_presets: true
```

Do not run a custom infinite `while True: sleep()` loop as the reference add-on does.

Use Home Assistant's scheduling helpers and lifecycle handling so configuration changes, unloads, and reloads work correctly.

The scheduled job must:
- skip if the previous full cycle is still running,
- not overlap runs,
- continue backing up other devices if one device fails,
- log per-device results,
- prune retention after successful backup operations.

---

# 7. Config Flow

## Initial setup

The initial configuration should be deliberately minimal.

### Step 1 — Welcome

Explain:

> WLED Backup Service automatically backs up WLED devices already configured in Home Assistant. You can later change the backup schedule, storage, retention, and contents from the integration settings.

### Step 2 — Basic defaults

Set:
- schedule enabled,
- backup interval,
- retention,
- storage,
- presets enabled.

Avoid asking the user to select WLED devices during initial setup. Discovery is dynamic.

### Single instance

Adding the integration a second time must be blocked by:

```json
"single_config_entry": true
```

## Options Flow

The Options Flow should be the main place for changing settings.

Recommended sections:

### Schedule
- enabled
- interval
- interval unit
- daily time

### Storage
- root
- subdirectory

### Contents
- cfg
- presets
- optional state

### Retention
- retain count
- retain age

### Behavior
- backup-before-restore
- verify after restore
- request device reboot after config restore, where appropriate

Use selectors, validation, and `data_description`/translation descriptions consistent with current HA UI guidance. citeturn214561search10

---

# 8. WLED discovery design

## Discovery source

The target population is:

> WLED devices already configured in Home Assistant's native `wled` integration.

Build a module:

```text
discovery.py
```

with an interface such as:

```python
@dataclass(frozen=True)
class WLEDDevice:
    device_id: str
    name: str
    host: str
    mac: str | None
    ha_device_id: str | None
    firmware_version: str | None
```

Provide:

```python
async def async_discover_wled_devices(
    hass: HomeAssistant,
) -> list[WLEDDevice]:
    ...
```

## Discovery identity priority

Use identity in this order:

1. WLED `deviceId` when available.
2. normalized WLED MAC.
3. HA WLED device/config-entry identity.
4. host as final fallback only.

Do not use a friendly name as identity.

## Host acquisition

Prefer information exposed by the existing WLED integration's config entry/device data.

If host information is unavailable, the discovery adapter may inspect suitable WLED entities or use the WLED integration runtime object if doing so is supported and stable for the target HA versions.

Do not scrape arbitrary `sensor.*` entities globally.

## Verify

Before backup, call:

```text
GET /json/info
```

and validate:
- HTTP 200,
- JSON response,
- WLED identity (`brand == "WLED"` where present),
- usable identity fields.

The `/json/info` endpoint is the canonical documented WLED device-information endpoint. citeturn526439search0

---

# 9. HTTP client architecture

Create:

```text
wled_client.py
```

Use Home Assistant's shared aiohttp client session rather than `requests`.

Do not block the event loop.

Suggested API:

```python
class WLEDClient:
    async def async_get_info(self) -> WLEDInfo
    async def async_get_config(self) -> dict[str, Any]
    async def async_get_presets_raw(self) -> bytes
    async def async_get_state(self) -> dict[str, Any]

    async def async_set_config(self, config: dict[str, Any]) -> None
    async def async_upload_presets(self, payload: bytes) -> None
    async def async_set_state(self, state: dict[str, Any]) -> None

    async def async_close(self) -> None
```

Use a bounded timeout per request.

Handle separately:
- connection error,
- timeout,
- non-2xx response,
- malformed JSON,
- unexpected content type,
- payload too large if limits are defined.

Do not log secrets or entire config payloads.

---

# 10. Restore strategy

## `cfg.json`

The WLED documentation says configuration is exposed at `/json/cfg`, and configuration updates are posted to JSON API routes such as `/json/cfg`. citeturn526439search0

Implement restore through the documented WLED JSON API.

Important:

- preserve unknown fields from the backup;
- do not "clean" fields unless the WLED documentation says they are unsupported;
- do not assume a config captured on one firmware version is safe on every future version;
- compare firmware versions and surface a warning when different;
- after applying config, verify with `/json/info` and `/json/cfg`.

## Presets

WLED explicitly documents `/presets.json` as the complete preset backup representation and the web UI restore workflow as file upload. citeturn569126search4

The implementation must therefore provide a reliable raw-file restore mechanism.

Do not invent a fake "preset-by-preset" reconstruction unless a direct filesystem/API upload mechanism is available and tested.

If the supported WLED endpoint for programmatic upload is not stable/documented for the project's supported firmware range, make preset restore a clearly isolated capability and implement it with an integration-tested method rather than silently claiming success.

## Backup before restore

Default:

```text
true
```

Before any destructive restore:
1. create a fresh backup of the target device;
2. only then apply the requested backup.

This gives the user a rollback point.

## Sequential operations

Never concurrently write to the same WLED device. WLED explicitly advises sequencing API calls. citeturn526439search0

Use a per-device `asyncio.Lock`.

---

# 11. Services / Actions

Use the integration domain:

```text
wled_backupservice
```

Suggested actions:

## `backup`

Immediately back up one or more WLED devices.

Target:
- device selector where feasible,
- otherwise a `device_id`/custom selector field that resolves to WLED devices.

Additional options:
- `include_presets`
- `include_state`
- `label` / reason

Return response data when the action is run with response support.

Example response:

```yaml
backups:
  - device_id: abc
    device_name: Kitchen WLED
    success: true
    path: /share/wled_backups/Kitchen_WLED/2026/09/27/024300
    files:
      - cfg.json
      - presets.json
    created_at: "2026-09-27T02:43:00+02:00"
```

## `restore`

Restore a selected backup.

Required:
- WLED device
- backup identifier/path

Additional:
- backup-before-restore
- restore config
- restore presets
- verify after restore
- reboot after restore

Destructive action.

Do not accept unrestricted arbitrary filesystem paths from service data. The action should accept a backup identifier generated/listed by the integration, then resolve it inside the configured backup root.

## `list_backups`

Read-only action returning available backups.

Inputs:
- optional WLED device
- optional limit
- optional include metadata

Return:
- backup ID
- device
- timestamp
- file list
- sizes
- firmware version
- integrity status

## `delete_backup`

Delete one backup identified by integration-generated ID.

Do not allow deletion outside the configured root.

## `prune`

Immediately execute the configured retention policy.

Optional:
- specific device
- dry-run

## `discover`

Force refresh of WLED device discovery.

Optional but valuable for debugging and automations.

## `backup_all`

Convenience action for all currently discovered devices.

It may internally use the same manager method as `backup`.

### Action registration

All actions must be registered from `async_setup`, as required by HA's current service/action guidance. citeturn569126search0

Create a proper `services.yaml`.

Descriptions must be understandable from the HA Actions UI.

---

# 12. Backup manager architecture

Create:

```text
manager.py
```

Suggested class:

```python
class WLEDBackupManager:
    async def async_discover_devices(...)
    async def async_backup_device(...)
    async def async_backup_all(...)
    async def async_restore(...)
    async def async_list_backups(...)
    async def async_delete_backup(...)
    async def async_prune(...)
```

The manager owns:
- discovery adapter,
- WLED client factory,
- storage service,
- retention service,
- locks,
- scheduler integration.

Do not put HTTP, filesystem, discovery, scheduling, and HA service registration into one `__init__.py`.

---

# 13. Storage service architecture

Create:

```text
storage.py
```

Interface:

```python
class BackupStorage:
    async def async_write_backup(...)
    async def async_read_backup(...)
    async def async_list(...)
    async def async_delete(...)
    async def async_prune(...)
```

All filesystem operations must be async-compatible.

For operations that have no async native equivalent, use HA's executor helpers appropriately rather than blocking the event loop.

Validate:
- root is an approved root,
- subdirectory is relative,
- no `..`,
- resolved path stays inside configured root,
- device directory contains sanitized data only.

Use SHA-256 hashes in `manifest.json` to detect corruption.

---

# 14. Retention policy

The product requirement says "how many backups to save" must be configurable.

Therefore v1 should make **count-based retention** the primary control.

Recommended default:

```text
30 backups per device
```

Support an optional age-based policy as a second safeguard.

Retention algorithm:

1. discover valid backup directories for each device;
2. sort by backup timestamp from manifest;
3. keep the newest N;
4. delete older entries;
5. optionally delete entries older than M days;
6. never delete an entry that cannot be confidently identified as one of this integration's backups.

A malformed/unrecognized directory must be left untouched.

---

# 15. Integrity and recovery

A backup is valid only when:
- `manifest.json` is parseable,
- schema version is supported,
- expected file hashes match,
- required artifacts exist.

When creating a backup:
1. fetch files,
2. write them to staging,
3. calculate hashes,
4. write manifest,
5. rename staging to final directory.

When restoring:
1. validate manifest,
2. verify hashes,
3. create safety backup if enabled,
4. restore sequentially,
5. verify.

---

# 16. Error handling

Define integration-specific exceptions:

```text
WLEDBackupError
WLEDConnectionError
WLEDValidationError
WLEDBackupNotFoundError
WLEDRestoreError
WLEDStorageError
```

Service actions must raise meaningful `HomeAssistantError` subclasses so the user receives an actionable HA error.

Translate user-facing errors via integration translation support, as HA recommends for service exceptions. citeturn214561search12

Log levels:

- `DEBUG`: request diagnostics, discovery details
- `INFO`: backup/restore start and successful completion
- `WARNING`: individual device unavailable, optional artifact missing, firmware mismatch
- `ERROR`: backup cycle failure, storage failure, restore failure

Never dump full `cfg.json`, `presets.json`, credentials, tokens, or network secrets into logs.

---

# 17. Runtime state and optional entities

The integration does not need normal device entities for the core feature.

Do **not** create one sensor per WLED unless there is a strong product requirement.

However, consider a small number of integration-level diagnostic entities in a later version:

- last successful backup
- last backup status
- backup count
- discovered device count
- last error

These should be `diagnostic`/appropriate entity-category entities if implemented.

For v1, service responses + diagnostics are sufficient.

---

# 18. Diagnostics

Implement:

```text
diagnostics.py
```

Diagnostics should expose safe metadata:
- integration version,
- config/options (with secrets removed),
- discovered WLED device count,
- device names,
- firmware versions,
- backup counts,
- last success/failure,
- storage root type,
- runtime state.

Do not include backup file contents.

This prepares the project for the stronger HA quality-scale expectations. citeturn214561search1

---

# 19. Repository structure

Target:

```text
hacs-wled-backupservice/
├── .github/
│   └── workflows/
│       ├── hassfest.yml
│       ├── hacs.yml
│       └── tests.yml
├── brand/
│   └── icon.png
├── custom_components/
│   └── wled_backupservice/
│       ├── __init__.py
│       ├── manifest.json
│       ├── config_flow.py
│       ├── const.py
│       ├── discovery.py
│       ├── wled_client.py
│       ├── manager.py
│       ├── storage.py
│       ├── retention.py
│       ├── diagnostics.py
│       ├── services.yaml
│       ├── quality_scale.yaml
│       ├── strings.json        # DO NOT use for runtime translations if HA custom-integration rules reject it
│       └── translations/
│           └── en.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── info.json
│   │   ├── cfg.json
│   │   └── presets.json
│   ├── test_config_flow.py
│   ├── test_discovery.py
│   ├── test_wled_client.py
│   ├── test_storage.py
│   ├── test_manager.py
│   ├── test_services.py
│   └── test_retention.py
├── hacs.json
├── README.md
├── info.md
├── LICENSE
└── pyproject.toml
```

**Translation note:** For a HACS custom integration, follow current HA custom localization guidance and manually provide `translations/en.json`; do not copy a core integration's `strings.json` pattern blindly. citeturn214561search4

---

# 20. Manifest

Target shape:

```json
{
  "domain": "wled_backupservice",
  "name": "WLED Backup Service",
  "codeowners": ["@tamaygz"],
  "config_flow": true,
  "documentation": "https://github.com/tamaygz/hacs-wled-backupservice",
  "integration_type": "service",
  "iot_class": "local_polling",
  "single_config_entry": true,
  "version": "1.0.0"
}
```

The final values must be checked against the current HA manifest schema before release.

Do not add third-party dependencies unless necessary.

Prefer stdlib + Home Assistant-provided libraries.

---

# 21. `hacs.json`

Minimum:

```json
{
  "name": "WLED Backup Service",
  "homeassistant": "2026.8.0"
}
```

The exact minimum HA version should be selected based on the APIs actually used, not arbitrarily.

Keep it as high as necessary to avoid compatibility hacks, but not higher than necessary for the initial release.

HACS requires the repository to have the correct integration structure and a root `hacs.json`. citeturn826650search0turn826650search5

---

# 22. Testing requirements

Target >95% test coverage for integration modules.

## Config flow tests

Test:
- initial setup,
- default values,
- invalid storage subdirectory,
- invalid interval,
- options flow,
- single entry behavior,
- config reload.

## Discovery tests

Test:
- zero WLED devices,
- one device,
- multiple devices,
- duplicated host,
- missing IP,
- unavailable WLED,
- identity based on MAC/device ID,
- friendly-name collision.

## HTTP tests

Test:
- success,
- timeout,
- connection refused,
- HTTP 404,
- HTTP 401/403 if applicable,
- invalid JSON,
- empty preset response,
- large preset response,
- unexpected content type.

Mock aiohttp rather than performing real network traffic.

## Storage tests

Test:
- correct directory structure,
- sanitization,
- path traversal rejection,
- atomic commit,
- manifest creation,
- hash calculation,
- corrupted backup detection,
- deletion,
- retention.

## Service tests

Test every action:
- valid invocation,
- selector resolution,
- no config entry,
- no discovered device,
- device offline,
- response data,
- error propagation.

HA specifically requires services/actions to remain registered independently of loaded config entries, so include this behavior in tests. citeturn569126search0

## Restore tests

Test:
- valid backup,
- invalid manifest,
- hash mismatch,
- firmware mismatch warning,
- backup-before-restore,
- config-only restore,
- presets-only restore,
- sequential requests,
- partial failure,
- verification failure.

---

# 23. Security requirements

Never:
- execute arbitrary shell commands,
- accept arbitrary filesystem paths,
- scan the whole LAN by default,
- expose full WLED config through logs,
- expose secrets through diagnostics,
- trust backup path strings from service calls,
- restore a backup into another device without explicit device selection.

Consider backup files potentially sensitive because WLED configuration may include network/service settings.

The README should explicitly say:

> Store backups only in a location you trust. WLED configuration backups may contain sensitive device configuration.

---

# 24. Firmware compatibility

The current HA WLED integration requires WLED 0.14.0 or newer. The custom integration should document which WLED versions have actually been tested rather than blindly claiming compatibility. citeturn760532search0

For v1:
- target currently maintained WLED firmware,
- test at least one ESP8266 and one ESP32 device,
- test multiple preset sizes,
- test both normal lighting presets and API-command presets.

Do not hard-code assumptions about future WLED JSON fields.

---

# 25. User experience

After installation the user should see approximately:

```text
Settings → Devices & services → Add integration
    → WLED Backup Service
    → Configure backup defaults
    → Done
```

There should be no:
- YAML,
- IP address entry,
- manual Docker setup,
- supervisor token,
- add-on install,
- filesystem mount configuration.

The only infrastructure prerequisite for remote storage is that the storage itself is already mounted by Home Assistant, using HA's normal network-storage mechanism. citeturn648556search0

---

# 26. README requirements

README should include:

1. What the integration does.
2. Screenshots/GIFs of:
   - setup,
   - options,
   - Actions.
3. Installation via HACS.
4. First-use instructions.
5. Supported storage locations.
6. Discovery behavior.
7. Backup layout.
8. All available actions.
9. Example YAML automations.
10. Restore warnings.
11. Troubleshooting.
12. Known limitations.
13. Supported HA/WLED versions.
14. Security warning.
15. Link to WLED docs.
16. Link to issue tracker.
17. License.

HACS values a useful README and repository metadata, and HACS's integration requirements include a valid manifest and one integration directory. citeturn826650search0turn826650search5

---

# 27. Example automations to document

## Manual scheduled backup through HA automation

The integration itself provides a native scheduler, but also document an action-based automation:

```yaml
alias: Backup WLED before weekend
trigger:
  - platform: time
    at: "03:00:00"
action:
  - action: wled_backupservice.backup_all
mode: single
```

The exact action syntax emitted in the final README must be verified against the final `services.yaml`.

## Backup before a known configuration change

```yaml
action:
  - action: wled_backupservice.backup
    target:
      device_id: YOUR_WLED_DEVICE
  - action: wled.some_future_action
```

Use examples that are actually compatible with HA's generated action UI.

---

# 28. Device targeting

Actions operating on one WLED should ideally use HA's **device-level target**, because the operation applies to the whole WLED device rather than one light entity.

Current HA guidance explicitly says device-level operations should target `device_id`, rather than using an arbitrary entity as a proxy. citeturn569126search0

However, because the backup integration does not own the WLED device entities, the implementation must resolve the target through the HA device registry.

Provide a robust resolver:

```python
async def async_resolve_target_devices(
    hass: HomeAssistant,
    call: ServiceCall,
) -> list[WLEDDevice]:
    ...
```

It should reject non-WLED devices clearly.

---

# 29. Optional "backup history" model

Do not create a database in v1.

The filesystem itself is the source of truth.

The manifest provides machine-readable metadata.

This keeps:
- migration simple,
- backups portable,
- corruption recovery easy,
- the integration stateless across restarts.

If performance later becomes a concern with very large backup histories, add an in-memory index/cache rather than introducing a persistent DB prematurely.

---

# 30. Migration/versioning

Config entry:

```python
VERSION = 1
```

Use config-entry migrations if the data/options schema changes.

Backup format:

```text
schema_version: 1
```

Never change the meaning of an existing backup schema silently.

Future backup readers must continue to understand older schemas where practical.

---

# 31. Release process

Initial release phases:

### Phase 0 — Repository bootstrap
- repo metadata,
- `manifest.json`,
- `hacs.json`,
- license,
- CI,
- brand assets,
- skeleton integration.

### Phase 1 — Discovery
- discover native HA WLED devices,
- verify device identity,
- unit tests.

### Phase 2 — Backup engine
- WLED client,
- cfg backup,
- presets backup,
- manifests,
- filesystem storage,
- retention.

### Phase 3 — Config/Options UI
- initial flow,
- options flow,
- translations,
- validation.

### Phase 4 — Actions
- backup,
- backup_all,
- restore,
- list_backups,
- delete_backup,
- prune,
- discover.

### Phase 5 — Diagnostics and hardening
- diagnostics,
- error handling,
- race-condition handling,
- concurrency locks,
- restore safety,
- corruption tests.

### Phase 6 — Release quality
- Hassfest,
- HACS action,
- full tests,
- coverage gate,
- documentation,
- GitHub release.

HACS recommends passing the HACS action and Hassfest before attempting default-repository inclusion. citeturn826650search1turn826650search3

---

# 32. Definition of Done

The project is complete only when all of the following are true:

- [ ] Public GitHub repository exists as `tamaygz/hacs-wled-backupservice`.
- [ ] Repository contains exactly one integration under `custom_components/wled_backupservice`.
- [ ] Integration installs through HACS.
- [ ] `manifest.json` validates.
- [ ] `hacs.json` validates.
- [ ] Brand icon is present.
- [ ] Config Flow works.
- [ ] The integration can only be added once.
- [ ] Options Flow works without YAML.
- [ ] Backup schedule is configurable.
- [ ] Backup destination is configurable.
- [ ] Retention count is configurable.
- [ ] WLED devices are discovered from HA's native WLED integration.
- [ ] No manual IP list is required.
- [ ] `/json/info` verification works.
- [ ] `/json/cfg` is backed up.
- [ ] `/presets.json` is backed up.
- [ ] Backups are timestamped and versioned.
- [ ] Backup metadata contains hashes.
- [ ] Backup writes are atomic.
- [ ] Retention pruning is safe.
- [ ] Backup action exists.
- [ ] Backup-all action exists.
- [ ] Restore action exists.
- [ ] List-backups action exists.
- [ ] Delete-backup action exists.
- [ ] Prune action exists.
- [ ] Discover action exists.
- [ ] Service actions are registered in `async_setup`.
- [ ] Service/action YAML is complete.
- [ ] Service response data works where useful.
- [ ] Restore is sequential per device.
- [ ] Optional safety backup before restore works.
- [ ] Restore validation works.
- [ ] Corrupt backup detection works.
- [ ] Diagnostics do not leak secrets.
- [ ] Translation files are present.
- [ ] README documents setup, storage, actions, restore, troubleshooting.
- [ ] Tests cover config flow.
- [ ] Tests cover discovery.
- [ ] Tests cover WLED HTTP behavior.
- [ ] Tests cover storage.
- [ ] Tests cover retention.
- [ ] Tests cover services.
- [ ] Tests cover restore.
- [ ] Coverage is >95% for integration code.
- [ ] Hassfest passes.
- [ ] HACS validation/action passes.
- [ ] At least one GitHub release exists before requesting HACS default listing.

---

# 33. Important implementation cautions for the coding agent

### Do not copy the reference add-on architecture

Do not introduce:
- Dockerfile,
- Supervisor token,
- `/data/options.json`,
- a second process,
- infinite sleep loop,
- HA Supervisor API calls.

This is a native custom component.

### Do not depend on the WLED IP sensor being enabled

The reference implementation requires IP sensors to be enabled. The new integration should not.

### Do not rely on friendly names for identity

Names change. MAC/device ID should be preferred.

### Do not assume `presets.json` is a small payload

Preset files can be large. Stream/read appropriately and test large payloads.

### Do not parallelize WLED write operations

WLED recommends sequential API calls for operations involving substantial data. citeturn526439search0

### Do not allow arbitrary restore paths

Resolve user-facing backup IDs against the configured storage root.

### Do not put secrets in logs

Especially important for configuration backups.

### Do not use core-only localization patterns blindly

Custom integrations need their own translations under `translations/`. citeturn214561search4

### Follow current HA 2026.x device-registry behavior

Newer HA versions now constrain devices to a single config entry and have deprecated multi-entry accessors such as `DeviceEntry.config_entries`. Code that interacts with the registry must use the current APIs, especially `config_entry_id`, and avoid deprecated properties. citeturn760532search5turn760532search14

---

# 34. Suggested implementation order for the coding agent

Implement and test in this order:

1. `const.py`
2. `manifest.json` + `hacs.json`
3. Config Flow + Options Flow
4. HA WLED discovery adapter
5. Async WLED client
6. Backup storage abstraction
7. Manifest/hash generation
8. Backup manager
9. Retention manager
10. Service registration
11. Restore implementation
12. Diagnostics
13. Translations
14. README
15. test suite + coverage
16. CI/Hassfest/HACS validation
17. release packaging

At every phase, keep the integration loadable by Home Assistant.

Do not implement all functionality in one giant module.

---

# 35. Architecture summary

```text
                 Home Assistant
                       │
                       ▼
             WLED Backup Service
                       │
          ┌────────────┴────────────┐
          │                         │
          ▼                         ▼
      Config Flow              HA Actions
      Options Flow             / Services
          │                         │
          └────────────┬────────────┘
                       ▼
              WLEDBackupManager
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   Discovery      WLED Client      Storage
        │              │              │
        ▼              ▼              ▼
 HA WLED devices   /json/info      /share
                   /json/cfg       /media
                   /presets.json   /backup
                   /json/state     /config
                                      │
                                      ▼
                              Backup directories
                                      │
                                      ▼
                                 Retention
```

The implementation should feel like a normal Home Assistant service integration—not like an add-on that happens to run next to Home Assistant.
