# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

## [0.1.2] - 2026-09-27

### Changed

- Release workflow publication.

- Documentation and release-preparation updates for the first public release.

## [1.0.0] - Pending release

### Added

- Native Home Assistant custom integration for WLED backup, restore, retention, and
  scheduled backup workflows.
- Config flow and multi-step options flow.
- Discovery of WLED devices from Home Assistant's native `wled` integration.
- Async WLED client for JSON endpoints and preset upload handling.
- Atomic filesystem backup storage with manifest and SHA-256 verification.
- Backup engine, restore engine, retention policy, diagnostics, and Home Assistant actions.
- Runtime translations, CI workflows, and an enforced 95% coverage gate.

### Changed

- Documentation now describes installation, storage layout, actions, restore warnings,
  known limitations, and release caveats.

### Fixed

- Restore safety-backup flow no longer re-enters the same per-device lock and deadlocks.