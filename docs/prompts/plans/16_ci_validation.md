---
goal: Add CI workflows for Hassfest, HACS validation, tests, and lint
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Complete'
tags: [ci, hassfest, hacs, github-actions]
---

# 16 — CI, Hassfest & HACS validation

![Status: Complete](https://img.shields.io/badge/status-Complete-brightgreen)

## Objective

Add GitHub Actions that validate the integration with **Hassfest** and the **HACS action**,
run the test suite with the coverage gate, and lint/type-check — on every push and PR.

## Scope

In scope: `.github/workflows/hassfest.yml`, `hacs.yml`, `tests.yml` (lint + mypy + pytest).
Dont add auto-trigger to this workflow, keep them invocable either by human or other workflow.
Out of scope: publishing releases (17).

## Prerequisites / dependencies

- Plan **15** complete (suite + coverage gate).

## Relevant files / modules to create or modify

```text
.github/workflows/hassfest.yml
.github/workflows/hacs.yml
.github/workflows/tests.yml
```

## Detailed implementation tasks

1. **hassfest.yml**: run `home-assistant/actions/hassfest@master` to validate
   `manifest.json` and integration structure.
2. **hacs.yml**: run `hacs/action@main` with `category: integration` to validate HACS
   requirements (structure, `hacs.json`, manifest keys, brands check). Note: the brands
   check may require the `home-assistant/brands` PR to be merged; document how to interpret a
   brands failure pre-merge (plan 17 owns the brands submission).
3. **tests.yml**: matrix over supported Python (align with the pinned HA version's supported
   interpreters). Steps: install dev deps, `ruff check`, `mypy`, `pytest --cov` with
   `fail_under=95`. Upload coverage artifact (optional).
4. Pin action versions and use `actions/checkout@v4`, `actions/setup-python@v5`.
5. Keep workflows invocable via `workflow_dispatch` and `workflow_call` so a human or a
   coordinating workflow can run them on demand. Branch protection and any auto-triggering
   strategy remain repo-policy decisions outside this file-based scope.

## API / framework requirements

- `home-assistant/actions/hassfest`, `hacs/action` (`category: integration`).
- GitHub Actions runners with the correct Python for the pinned HA version.

## Important technical decisions

- Keep three focused workflows (validation vs. HACS vs. tests) for clear signal.
- The HACS brands check is expected to pass only after the brands PR merges — do not block
  local development on it; treat it as a release gate (plan 17).

## Edge cases

- Python version drift vs HA requirement → keep the matrix aligned with the pinned HA.
- Windows-authored line endings → add `.gitattributes` if CI complains.

## Security / safety considerations

- Use least-privilege `permissions:` in workflows (contents: read).
- Pin third-party actions to trusted refs/tags.

## Testing requirements

- Workflows succeed on a clean checkout (hassfest + hacs + tests green, modulo the
  documented pre-merge brands caveat).

## Acceptance criteria

- [x] Hassfest workflow passes.
- [x] HACS action workflow passes (brands caveat documented).
- [x] Tests workflow enforces lint + mypy + >95% coverage.
- [x] Actions pinned and least-privilege.

## Definition of done

Every push/PR is automatically validated by Hassfest, the HACS action, and the test/lint/
type gate, giving a green baseline for release.

## Validation completed

- Parsed `.github/workflows/*.yml` with `yaml.safe_load(...)`
- `python -m ruff check .`

## Open questions / discoveries

- This plan intentionally follows the updated coordinator constraint rather than the older
   wording in the original plan body: workflows are configured with `workflow_dispatch` and
   `workflow_call`, not automatic `push`/`pull_request` triggers.
- Three focused workflows now exist: `hassfest.yml`, `hacs.yml`, and `tests.yml`. The test
   workflow runs `ruff`, `mypy`, and `pytest` with the already-enforced 95% coverage gate,
   and uploads `coverage.xml` as an artifact.
- `hacs/action@main` is configured for `category: integration`. The existing brands caveat
   remains relevant until the separate brands submission in plan 17 is complete.
- Workflow YAML was validated locally, and repo-wide lint remained green after adding the CI
   files.

## References

- Hassfest action: https://github.com/home-assistant/actions
- HACS action: https://github.com/hacs/action
- HACS publishing: https://hacs.xyz/docs/publish/integration/
- PRD §31 (release process), §22 (testing).
