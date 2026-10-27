# Repository workflow

## Git Flow

- Use `main` for released, production-ready data and automation.
- Use `develop` as the integration branch for upcoming changes.
- Create feature branches from `develop` and name them `feature/<short-description>`.
- Create bug-fix branches from `develop` and name them `bugfix/<short-description>`.
- Create release branches from `develop` and name them `release/<version-or-date>`; merge them into both `main` and `develop`.
- Create urgent production fixes from `main` and name them `hotfix/<short-description>`; merge them into both `main` and `develop`.
- Do not use the `codex/` branch prefix.
- Do not push directly to `main` or `develop`; use pull requests and wait for required checks.
- Keep the existing `dwhao84/automated-housing-update` branch name for the scheduled data-update workflow.

## Changes and validation

- Keep commits focused and write concise Traditional Chinese commit messages.
- Do not modify generated housing data unless the task explicitly requires a data update.
- Before opening a pull request, run the tests and validation commands relevant to the changed files.
- Pull requests into `main` or `develop` must pass `validate-housing-data`.
