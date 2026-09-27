# WLED Backup Service

WLED Backup Service is a native Home Assistant custom integration that backs up,
restores, prunes, and schedules backups for WLED devices already configured in Home
Assistant's built-in `wled` integration.

It stores validated filesystem backups containing WLED configuration, device metadata,
optional presets, and optional runtime state snapshots. Restore is designed to be safe by
default, with a rollback safety backup, device-identity checks, verification, and clear
partial-result reporting.

## What It Does

- Discovers WLED devices from Home Assistant's native `wled` integration.
- Backs up `cfg.json` and `info.json` for each device.
- Optionally includes `presets.json` and a `state.json` snapshot.
- Restores configuration and, when supported and verified, presets.
- Prunes old backups by count and age.
- Runs scheduled backup cycles with overlap protection.
- Exposes Home Assistant actions for backup, restore, list, delete, prune, and discovery.

## Requirements

- Home Assistant version declared in [hacs.json](hacs.json): `2025.12.0` or newer.
- One or more WLED devices already configured through Home Assistant's native `wled`
	integration.
- A trusted storage location under one of Home Assistant's supported roots: `/share`,
	`/media`, `/backup`, or `/config`.

## Installation

[![Open your Home Assistant instance and add this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tamaygz&repository=hacs-wled-backupservice&category=integration)

If the button above does not open your Home Assistant instance correctly, add this
repository to HACS manually as a custom repository in the `Integration` category, then
install `WLED Backup Service`, restart Home Assistant, and add the integration from
`Settings` → `Devices & services`.

<details>
<summary>Manual installation</summary>

1. Copy `custom_components/wled_backupservice` into your Home Assistant
   `custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration from `Settings` → `Devices & services`.

</details>

## First Use

The initial setup flow is intentionally minimal. After adding the integration, open the
options flow to configure:

- backup schedule
- storage root and subdirectory
- backup contents
- retention policy
- restore behavior

The integration uses a single config entry and operates on the WLED devices Home Assistant
already knows about.

## Options Overview

### Schedule

- Enable or disable scheduled backups.
- Run every N minutes, hours, or days.
- If the schedule is exactly every 1 day, `daily_time` is used for a predictable daily run.
- Longer day-based schedules remain interval-based.

### Storage

- Supported storage roots: `/share`, `/media`, `/backup`, `/config`.
- Default storage root: `/share`.
- Default subdirectory: `wled_backups`.
- Subdirectories are normalized and must stay relative to the chosen root.

### Contents

- `cfg.json` and `info.json` are always included.
- `presets.json` can be included.
- `state.json` can be included as a snapshot of current runtime state.
- `create_archive` is currently reserved for future use and does not change storage format.

### Retention

- Keep the newest N backups per device.
- Optionally prune backups older than a configured number of days.
- Pruning supports dry-run reporting.

### Restore Behavior

- Safety backup before restore is enabled by default.
- Post-restore verification is enabled by default.
- Optional reboot after restore is supported.

## Discovery Behavior

This integration does not maintain a separate device inventory. It only operates on WLED
devices already configured through Home Assistant's native `wled` integration.

Discovery uses Home Assistant config entries and the device registry to build a stable list
of WLED targets. Non-WLED targets are rejected by the action handlers.

## Storage Layout

Backups are stored as validated directories with a manifest and file hashes:

```text
<storage-root>/<subdir>/<device_name>_<device_id>/YYYY/MM/DD/HHMMSS/
	manifest.json
	cfg.json
	info.json
	presets.json        # optional
	state.json          # optional
```

Example:

```text
/share/wled_backups/Kitchen_Strip_wled-aabbccddeeff/2026/09/27/083336/
	manifest.json
	cfg.json
	info.json
	presets.json
```

## Home Assistant Actions

The integration registers the following actions:

- `wled_backupservice.backup`
- `wled_backupservice.backup_all`
- `wled_backupservice.restore`
- `wled_backupservice.list_backups`
- `wled_backupservice.delete_backup`
- `wled_backupservice.prune`
- `wled_backupservice.discover`

### Backup A Selected WLED Device

```yaml
action: wled_backupservice.backup
target:
  device_id: YOUR_WLED_DEVICE_ID
data:
  include_presets: true
  include_state: false
```

### Backup All Discovered WLED Devices

```yaml
action: wled_backupservice.backup_all
data:
  include_presets: true
  include_state: false
```

### Restore A Backup

```yaml
action: wled_backupservice.restore
target:
  device_id: YOUR_WLED_DEVICE_ID
data:
  backup_id: Kitchen_Strip_wled-aabbccddeeff/2026/09/27/083336
  backup_before_restore: true
  restore_config: true
  restore_presets: true
  verify_after_restore: true
  reboot_after_restore: false
```

### List Backups

```yaml
action: wled_backupservice.list_backups
target:
  device_id: YOUR_WLED_DEVICE_ID
data:
  limit: 10
```

### Delete A Backup

```yaml
action: wled_backupservice.delete_backup
data:
  backup_id: Kitchen_Strip_wled-aabbccddeeff/2026/09/27/083336
```

### Dry-Run A Prune Operation

```yaml
action: wled_backupservice.prune
target:
  device_id: YOUR_WLED_DEVICE_ID
data:
  dry_run: true
```

### Discover Known WLED Devices

```yaml
action: wled_backupservice.discover
```

## Restore Warnings

Restore is a destructive action.

- Restoring `cfg.json` can overwrite device settings.
- Restore may change connectivity-related configuration.
- Restore can optionally reboot the device.
- A backup is refused if the live device identity does not match the backup identity.
- Firmware mismatches are reported as warnings, not silent success.
- Verification can still report partial failure after configuration was applied.

## Known Limitations

- Preset restore is only attempted when the `/edit` upload path is both supported and
	verified for the target device/firmware path.
- `state.json` can be backed up, but current restore applies configuration and presets only;
	runtime state snapshots are not restored.
- The `label` field accepted by the `backup` action is reserved for future use and does not
	currently change the stored backup.
- `create_archive` is a placeholder option for future archive export support.
- Real hardware verification of preset restore across multiple firmware variants is still
	pending.

## Supported Versions

- Minimum Home Assistant version: `2025.12.0` (from [hacs.json](hacs.json)).
- Repository development and automated tests currently run against Home Assistant `2024.3.3`
	for local tooling compatibility, but the declared installation floor remains `2025.12.0`.
- Automated fixture coverage models WLED payloads based on `0.16.0` and mismatch handling
	against `0.17.0` payloads. This is not a substitute for a full real-hardware firmware
	support matrix.

## Troubleshooting

### No Devices Are Found

- Confirm your WLED devices are already working in Home Assistant's native `wled`
	integration.
- Re-run `wled_backupservice.discover` to inspect what Home Assistant currently exposes.

### Restore Reports `unsupported` For Presets

- The integration intentionally skips preset restore unless the WLED preset upload path is
	marked supported and verified.
- Configuration restore can still succeed even when preset restore remains unavailable.

### Restore Fails On Device Identity

- The integration checks live device identity against the backup manifest.
- Re-select the correct target device and verify the device was not replaced or reflashed to
	a different identity.

### Prune Or Backup Path Errors

- Confirm the selected storage root exists in your Home Assistant environment.
- Confirm the configured subdirectory stays within the selected storage root.

## Security

Store backups only in a location you trust. Backups can contain full WLED configuration,
device metadata, optional presets, and optional runtime state snapshots.

Treat restore operations carefully, especially when restoring onto production lighting
devices or devices with connectivity-related configuration.

## Brands And HACS Default Listing

This repository includes local brand assets for repo-level validation. HACS default listing
still requires a separate PR to the `home-assistant/brands` repository under
`custom_integrations/wled_backupservice/`.

Until that upstream brands PR is merged, treat HACS brands-related validation failures as a
release-preparation issue rather than an implementation failure.

## Additional References

- WLED documentation: https://kno.wled.ge/
- HACS publish docs: https://hacs.xyz/docs/publish/integration/
- Issue tracker: https://github.com/tamaygz/hacs-wled-backupservice/issues

## License

This project is licensed under the [MIT License](LICENSE).