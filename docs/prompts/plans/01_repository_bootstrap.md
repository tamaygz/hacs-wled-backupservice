---
goal: Bootstrap the repository skeleton, tooling, and test scaffolding
version: 1.0
date_created: 2026-09-27
last_updated: 2026-09-27
owner: '@tamaygz'
status: 'Planned'
tags: [bootstrap, tooling, structure]
---

# 01 — Repository bootstrap & tooling

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Objective

Create the empty-but-valid repository structure, Python tooling, license, and the test
harness so that every later plan has a place to add code and tests, and so `pytest` runs
green against an empty suite.

## Scope

In scope: directory layout, `pyproject.toml`, `LICENSE`, `.gitignore`, README/info
placeholders, test scaffolding (`tests/`, `conftest.py`, fixtures folder), an empty
`custom_components/wled_backupservice/` package placeholder. Out of scope: any integration
logic, manifest content, CI (plan 16).

## Prerequisites / dependencies

None (first plan). Empty git repo already initialized.

## Relevant files / modules to create or modify

```text
custom_components/wled_backupservice/__init__.py     # empty placeholder (real content in 03)
tests/__init__.py
tests/conftest.py
tests/fixtures/.gitkeep
pyproject.toml
.gitignore
LICENSE
README.md            # skeleton (full content in 17)
info.md              # skeleton (full content in 17)
.pre-commit-config.yaml (optional)
```

## Detailed implementation tasks

1. Create the directory tree exactly as in PRD §19 (create empty dirs with `.gitkeep`
   where needed; do not yet create module bodies owned by later plans).
2. `pyproject.toml`:
   - `[build-system]` not required (integration is not a wheel); configure only tooling.
   - Configure `pytest`, `ruff`, `mypy` and coverage. Add dev deps:
     `pytest`, `pytest-homeassistant-custom-component`, `pytest-asyncio`, `pytest-cov`,
     `homeassistant`, `aioresponses` (or `pytest-aiohttp`/`aresponses`) for HTTP mocking,
     `ruff`, `mypy`.
   - Pin `homeassistant` to a version consistent with the `hacs.json` minimum chosen in
     plan 02 (leave a TODO note to reconcile). Prefer the latest stable HA at
     implementation time and record the exact version used.
   - Configure `ruff` to follow HA's lint conventions where practical.
   - Configure coverage `--cov=custom_components/wled_backupservice` with `fail_under`
     initially unset (raised to 95 in plan 15).
3. `.gitignore`: Python, venv, `__pycache__`, coverage artifacts, `.mypy_cache`, IDE files.
4. `LICENSE`: MIT (owner `@tamaygz`) unless the owner specifies otherwise — flag as a
   decision to confirm at release.
5. `README.md` / `info.md`: minimal skeleton with title + one-line description + a
   "work in progress" note. Full content is plan 17.
6. `tests/conftest.py`: enable the `pytest-homeassistant-custom-component` plugin
   (`pytest_plugins = "pytest_homeassistant_custom_component"`), add an
   `auto_enable_custom_integrations` autouse fixture (the plugin provides
   `enable_custom_integrations`). Add a shared `hass` usage note.
7. Add a trivial smoke test `tests/test_import.py` that imports the package to prove the
   harness works; later plans replace/extend it.

## API / framework requirements

- `pytest-homeassistant-custom-component` provides `hass`, `enable_custom_integrations`,
  `aioclient_mock`, `MockConfigEntry`, etc. Confirm the plugin version matches the pinned
  `homeassistant` version (they are released in lockstep).

## Important technical decisions

- Use `pytest-homeassistant-custom-component` (the community standard) rather than hand-
  rolling HA test fixtures.
- Keep the integration a non-packaged source tree (HACS deploys `custom_components/`
  directly); `pyproject.toml` is for tooling/tests only.

## Edge cases

- Windows dev environment: ensure path handling in tests is OS-agnostic (`pathlib`, `tmp_path`).
- Ensure `tests/fixtures/` exists even before real fixtures are added.

## Security / safety considerations

- Do not commit secrets or real device backups. Add patterns to `.gitignore` for
  `*.local`, `secrets.*`.

## Testing requirements

- `pytest` runs and passes with the smoke test.
- `ruff check` and `mypy` run without configuration errors (may report zero files).

## Acceptance criteria

- [ ] Directory tree from PRD §19 exists.
- [ ] `pytest` executes and the smoke test passes.
- [ ] `pyproject.toml` declares all dev/test dependencies and tool config.
- [ ] `LICENSE`, `.gitignore`, README/info skeletons exist.

## Definition of done

Repository can be cloned, dev dependencies installed, and `pytest`/`ruff`/`mypy` run
without harness errors. No integration logic yet.

## References

- HA custom-component testing plugin: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component
- HACS integration structure: https://hacs.xyz/docs/publish/integration/
- PRD §19 (repository structure), §22 (testing requirements).
