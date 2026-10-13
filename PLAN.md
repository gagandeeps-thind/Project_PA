# PLAN

## Goal
Get every check that CI runs green locally, and close the coverage and tooling gaps found while
setting the repo up for autonomous agent work (2026-10-12).

## Constraints
- Follow CLAUDE.md: one item per commit, gate green, conventional commit on a feature branch, never push to main/master.
- Items marked `[human]` touch danger zones (CI, migrations, lockfiles, .env, Dockerfile, deploy runbook) and need a human.
- The working tree contains uncommitted mixed WIP from earlier sessions. Do not commit files unrelated to the item.

## Tasks

- [x] backend: diagnose the crystal ledger reconciliation failure
  - `python scripts/reconcile_ledger.py --check` fails on the dev DB (seen: `challenger.09270021@example.com` ledger 200 vs wallet 100;
    `growth_g3_test_seeker@example.com` ledger 100 vs wallet 0). The count changed while the test suites ran.
  - Determine whether a code path writes `mana_crystals` without `services.ledger.apply_crystal_delta`, or whether test cleanup deletes users/ledger rows partially.
  - Acceptance: a written root cause in the commit body, plus a failing-then-passing regression test in the owning suite.
    After running all 13 CI suites, `reconcile_ledger.py --check` exits 0 for every user the suites create.

- [ ] [human] data: clean the pre-existing ledger orphans out of the local dev DB
  - Root cause fixed in `fix/ledger-orphan-rows`, but rows written before the fix remain in `fitness_mvp.db`
    (orphans for missing users 14, 21, 22, 23; user 6 inherited row 68 from a deleted account).
  - Acceptance: delete those rows (or recreate the dev DB with `alembic upgrade head`); `reconcile_ledger.py --check` exits 0.

- [x] backend: route `DELETE /api/v1/users/{id}` through `growth_safety.erase_player`
  - Today it hard-deletes the users row and its crystal ledger rows (financial records must be anonymised and kept,
    PRD-009) while leaving runs, route points, courses, challenges and attempts behind. SQLite then reuses the id,
    so a new account can inherit another person's GPS history.
  - Acceptance: the endpoint anonymises via `erase_player` and keeps the tombstone row and ledger;
    the GDPR suite asserts route points are gone and the ledger still reconciles.

- [x] backend: resolve the OpenAPI contract drift
  - `python scripts/check_openapi_drift.py` exits 1 against the current working tree.
  - Acceptance: confirm that every schema difference comes from an intended API change in the WIP, then run
    `python scripts/check_openapi_drift.py --write`; the drift check exits 0 and the diff to `Documentation/openapi.json` contains only intended changes.

- [ ] [human] ci: add `python tests/test_mvp_gdpr_and_email_uniqueness.py` to `.github/workflows/ci.yml`
  - The suite exists and passes locally, but CI does not run it. After the CI step is added, an agent adds it to `BACKEND_TESTS` in `.claude/hooks/gate.sh`.
  - Acceptance: the CI job runs the suite and it passes.

- [ ] [human] ci: add jobs for `Osiris_admin_web` (`npm run build`) and `Osiris_customer` (`flutter analyze`, `flutter test`)
  - Today CI covers the backend only. Both commands pass locally.
  - Acceptance: a pull request that touches either app runs its job, and the job passes.

- [x] admin web: remove dead Vite template files
  - `index.html` loads `/src/main.tsx`; `src/main.ts`, `src/counter.ts`, `src/style.css` are only referenced by each other.
  - Acceptance: files deleted, `npm run build` passes, the dev server renders the login page.

- [x] backend: make mypy clean for `spatial_utils.py` and `ml_referee.py`
  - CI's mypy step is `continue-on-error` and currently reports 640 errors in 6 files.
  - Acceptance: the CI mypy command reports zero errors located in these two files; behaviour is unchanged and all backend suites still pass.

- [x] backend: convert `models.py` to SQLAlchemy 2.0 typed mappings (`Mapped[...]` / `mapped_column`)
  - Found 2026-10-12: `spatial_utils.py` and `ml_referee.py` already have zero mypy errors. The 640 errors are in
    main.py (386), growth_communities/api/safety/social (298) and services/ledger.py (1), and ~95% are arg-type /
    assignment errors because legacy `Column(...)` attributes type as `Column[int]` instead of `int`.
  - Acceptance: identical DDL (`Base.metadata` produces the same tables, columns, types, nullability, indexes and
    constraints before and after; no migration); all backend suites pass; the CI mypy error count drops substantially.

- [ ] [human] ci: make the mypy step blocking
  - Since the typed-models refactor the CI mypy command reports zero errors, but the CI workflow still marks the
    step `continue-on-error: true`, so a regression would not fail CI. After the CI edit, an agent adds mypy to gate.sh.
  - Acceptance: the mypy step has no `continue-on-error` and passes.

- [ ] [human] tooling: decide on formatters (`ruff format` for the backend, `dart format` for the apps)
  - None are adopted (`ruff.toml` defers formatting). `.claude/hooks/format.sh` is a no-op until one is chosen.
  - Acceptance: decision recorded; if adopted, a one-off formatting commit, then format.sh and CLAUDE.md are updated with the command.

- [ ] [human] tooling: decide on lint and tests for `Osiris_admin_web`
  - There is no ESLint config and no test runner; only `tsc` (via `npm run build`) guards it.
  - Acceptance: decision recorded; if adopted, the scripts are added to `package.json` and wired into the gate.
