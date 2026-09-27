---
goal: Add CI workflows for Hassfest, HACS validation, tests, and lint
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Planned'
tags: [ci, hassfest, hacs, github-actions]
---

# 16 — CI, Hassfest & HACS validation

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Objective

Add GitHub Actions that validate the integration with **Hassfest** and the **HACS action**,
run the test suite with the coverage gate, and lint/type-check — on every push and PR.

## Scope

In scope: `.github/workflows/hassfest.yml`, `hacs.yml`, `tests.yml` (lint + mypy + pytest).
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

1. **hassfest.yml**: run `home-assistant/actions/hassfest@master` on push/PR to validate
   `manifest.json` and integration structure.
2. **hacs.yml**: run `hacs/action@main` with `category: integration` to validate HACS
   requirements (structure, `hacs.json`, manifest keys, brands check). Note: the brands
   check may require the `home-assistant/brands` PR to be merged; document how to interpret a
   brands failure pre-merge (plan 17 owns the brands submission).
3. **tests.yml**: matrix over supported Python (align with the pinned HA version's supported
   interpreters). Steps: install dev deps, `ruff check`, `mypy`, `pytest --cov` with
   `fail_under=95`. Upload coverage artifact (optional).
4. Pin action versions and use `actions/checkout@v4`, `actions/setup-python@v5`.
5. Ensure workflows run on `push` and `pull_request` and are required for merge (document in
   README/CONTRIBUTING; branch protection is a repo setting, not a file).

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

- [ ] Hassfest workflow passes.
- [ ] HACS action workflow passes (brands caveat documented).
- [ ] Tests workflow enforces lint + mypy + >95% coverage.
- [ ] Actions pinned and least-privilege.

## Definition of done

Every push/PR is automatically validated by Hassfest, the HACS action, and the test/lint/
type gate, giving a green baseline for release.

## References

- Hassfest action: https://github.com/home-assistant/actions
- HACS action: https://github.com/hacs/action
- HACS publishing: https://hacs.xyz/docs/publish/integration/
- PRD §31 (release process), §22 (testing).
