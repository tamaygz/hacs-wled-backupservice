---
goal: Complete documentation, quality-scale metadata, brands submission, and cut the first GitHub release
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Blocked'
tags: [documentation, release, hacs, branding]
---

# 17 — Documentation & release

![Status: Blocked](https://img.shields.io/badge/status-Blocked-red)

## Objective

Ship complete user documentation, quality-scale metadata, the brands submission, and the
first tagged GitHub release so the integration is installable and eligible for HACS default
listing.

## Scope

In scope: `README.md`, `info.md`, `quality_scale.yaml`, brands PR, release tagging,
firmware/HA version documentation. Out of scope: new features.

## Prerequisites / dependencies

- Plan **16** complete (CI green). All functional plans complete.

## Relevant files / modules to create or modify

```text
README.md
info.md
custom_components/wled_backupservice/quality_scale.yaml
CHANGELOG.md
# external: PR to home-assistant/brands (custom_integrations/wled_backupservice/)
```

## Detailed implementation tasks

1. **README** (PRD §26) — cover all 17 points: what it does; screenshots/GIFs of setup,
   options, actions; HACS install; first-use; supported storage locations; discovery
   behavior; backup layout; all actions with example YAML; **restore warnings**;
   troubleshooting; known limitations (incl. preset-restore firmware caveat); supported
   HA/WLED versions; the security warning ("Store backups only in a location you trust…");
   link to WLED docs; issue tracker; license.
2. **Example automations** (PRD §27) — verify the emitted `action:` syntax against the final
   `services.yaml` before publishing (do not ship untested YAML).
3. **`quality_scale.yaml`** — record the integration's status against the current HA quality
   scale rules (service registration, config-flow test coverage, common modules, branding,
   diagnostics, >95% coverage). Mark items done/todo honestly.
4. **Firmware/HA versions** (PRD §24): document the WLED firmware versions actually tested
   (at least one ESP8266 + one ESP32, multiple preset sizes, normal + API-command presets)
   and the minimum HA version (matching `hacs.json`). **Verify the preset `/edit` restore
   path on real hardware** and document supported/unsupported firmware for preset restore.
5. **Brands submission**: open a PR to `home-assistant/brands` adding
   `custom_integrations/wled_backupservice/` icon+logo. Note in README that the brands PR
   must merge before requesting HACS default inclusion.
6. **Release**: bump `manifest.json` `version` (semver), update `CHANGELOG.md`, tag and
   publish a GitHub Release (HACS prefers releases). Confirm hassfest + HACS action are
   green on the tagged commit.
7. Update `docs/prompts/plans/0_index.md` statuses to ✅ as phases complete.

## API / framework requirements

- HACS default-listing prerequisites: valid repo structure, `hacs.json`, manifest, merged
  brands, a published release, passing HACS action + hassfest.
- Quality scale rules (current).

## Important technical decisions

- Do not claim WLED-version compatibility that wasn't tested (PRD §24, §33).
- Ship only action YAML verified against the final `services.yaml`.
- License confirmed (from plan 01).

## Edge cases

- Preset restore unsupported on some firmware → document clearly rather than implying
  universal support.
- HACS default listing may lag brands merge → README sets expectations.

## Security / safety considerations

- README security warning about sensitive backup contents is mandatory (PRD §23, §26).
- Restore/destructive warnings prominent.

## Testing requirements

- README example automations validated against `services.yaml`.
- Release commit passes hassfest + HACS action + tests.

## Acceptance criteria (maps to PRD §32 Definition of Done)

- [x] README documents setup, storage, actions, restore, troubleshooting, versions, security.
- [x] `quality_scale.yaml` present and honest.
- [ ] Brands PR opened (and tracked to merge).
- [ ] First GitHub release published; manifest version bumped.
- [ ] Hassfest + HACS + tests green on the release commit.
- [ ] Installable via HACS.

## Definition of done

The integration is documented, released, and HACS-installable, with an honest quality-scale
record and brands submission in progress/merged — satisfying the PRD §32 checklist.

## Validation completed

- Parsed `.github/workflows/*.yml` with `yaml.safe_load(...)`
- Parsed README action YAML examples against `custom_components/wled_backupservice/services.yaml`
- `python -m pytest`
- `python -m ruff check .`

## Open questions / discoveries

- In-repo release-preparation artifacts are now present: `README.md`, `info.md`,
   `custom_components/wled_backupservice/quality_scale.yaml`, `CHANGELOG.md`, and a new
   `release.yml` GitHub Actions workflow.
- The release workflow is branch-aware: it checks out the branch used to invoke the manual
   run, commits the version bump back to that same branch, tags the resulting commit, and
   publishes a GitHub release from it.
- The workflow accepts only HACS-friendly semantic versions without a leading `v`, then tags
   the release commit as `v<version>` for GitHub releases.
- README now includes HACS, release, test-gate, Hassfest, and HACS-validation badges to make
   installation status and repo health easier to see.
- This plan remains blocked on external steps that cannot be completed from the local
   repository alone: opening the `home-assistant/brands` PR, real-hardware preset-restore
   verification across the documented firmware matrix, invoking the release workflow to
   publish the first GitHub release, and confirming green workflow runs on that released
   commit.

## References

- HACS publish/default inclusion: https://hacs.xyz/docs/publish/integration/ and https://hacs.xyz/docs/publish/include/
- HA brands: https://github.com/home-assistant/brands
- Quality scale: https://developers.home-assistant.io/docs/core/integration-quality-scale/
- PRD §24, §26, §27, §31, §32.
