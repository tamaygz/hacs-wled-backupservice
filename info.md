# WLED Backup Service

Back up and restore WLED devices already configured in Home Assistant's native `wled`
integration.

WLED Backup Service provides:

- on-demand device backups
- scheduled backup cycles
- retention pruning
- validated backup manifests and file hashes
- configuration restore with safety-backup protection
- preset restore when the WLED upload path is supported and verified

Backups are stored under one of Home Assistant's trusted storage roots and can include
configuration, device metadata, presets, and optional runtime state snapshots.

Restore is destructive and can affect connectivity or reboot the target device. Review the
README for installation, storage guidance, known limitations, and restore warnings.
