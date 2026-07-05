# Docs Index

Use this page as the starting point for the current documentation set.

## Setup And Running

- `docs/run-project.md`
  - local setup
  - backend/frontend startup
  - MediaPipe model setup
  - migration command
  - common troubleshooting

## Current System State

- `docs/current-architecture.md`
  - how the system works today
  - which modules own which responsibilities
  - why storage is still intentionally split

- `docs/data-storage-model.md`
  - current persistence model
  - live SQLite table structure
  - JSON test history and file-based DTW/recording storage

- `docs/dtw-recording-flow.md`
  - websocket recording flow
  - canonical DTW session ids
  - patient-scoped DTW lookup
  - shared keypoint contract

## API Reference

- `docs/swagger-api-docs.md`
  - Swagger/OpenAPI URLs
  - what is documented
  - important current API behavior notes

## Verification

- `docs/backend-phase-6-verification.md`
  - final backend verification scope
  - automated integration coverage
  - historical migration results

## Historical Audit And Refactor Record

- `docs/backend-phase-0-audit.md`
  - original backend audit findings
  - repeat-audit deltas
  - resolution update for current branch

- `docs/backend-refactor-plan.md`
  - original backend refactor phase plan
  - implementation status notes per phase

- `docs/frontend-backend-integration-cleanup.md`
  - route/auth/profile/history cleanup log

- `docs/frontend-cleanup-log.md`
  - broader frontend cleanup history

- `docs/repo-cleanup-log.md`
  - repository/storage cleanup history

## Long-Term Follow-Up

- `docs/long-term-backend-cleanup.md`
  - future-facing cleanup ideas still left after the refactor

## Suggested Reading Order

If you are new to the repo:

1. `docs/run-project.md`
2. `docs/current-architecture.md`
3. `docs/data-storage-model.md`
4. `docs/dtw-recording-flow.md`
5. `docs/swagger-api-docs.md`

If you want refactor history:

1. `docs/backend-phase-0-audit.md`
2. `docs/backend-refactor-plan.md`
3. `docs/backend-phase-6-verification.md`
