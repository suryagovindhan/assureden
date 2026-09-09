# AssureDen completion roadmap

The canonical application is `backend/` (FastAPI/PostgreSQL) and `frontend/`
(React). The root `server/`/`agent/` and nested `AssureDen/` trees are legacy
references. Their features and protocols must not be counted as integrated
capabilities of the canonical application.

## Product contract

AssureDen is a deterministic, no-LLM automation platform:

Recorder → DraftAsset review → BusinessAction / Flow / TestCase promotion →
versioned execution context → agent execution → results, evidence and reports.

It includes reusable multi-locator objects, assertions, data-driven and manual
checks, environment profiles, suites, templates, parallel execution and cron.
Organization isolation and role permissions apply throughout.

## Delivery checklist

- [x] Repair the frontend production build against the locked Material UI version.
- [x] Merge Phase 4/5 migration branches without rewriting their history.
- [x] Declare scheduler runtime and development-test dependencies.
- [x] Execute Reports SQL on PostgreSQL; correct weekly buckets and duration weighting.
- [x] Add PostgreSQL report regressions and build/test CI.
- [ ] Establish reproducible dependency lockfiles for the supported backend runtime.
- [ ] Preserve locators, assertions, timeouts, optionality and input resolution in snapshots.
- [ ] Connect a modern authenticated agent to the HTTP poll/callback protocol.
- [ ] Wire flow references through API/editor and implement immutable flow revisions.
- [ ] Enforce tenant-reference validation and mutation permissions consistently.
- [ ] Require safe secret configuration; prevent persisted plaintext run secrets.
- [ ] Repair lease renewal, capacity, terminal-state fencing, abort and retries.
- [ ] Make event allocation transactional; repair scheduler/offline-detector paths.
- [ ] Complete agent evidence upload and authenticated artifact viewing.
- [ ] Complete dashboard, queue, SSE resumption and report timezone handling.
- [ ] Implement recorder drafts and governed promotion with provenance.
- [ ] Implement BusinessAction inputs/outputs and reusable composition.
- [ ] Implement global/environment/generated/secret datasets and manual outcomes.
- [ ] Implement execution profiles, suite runs, templates and bounded parallelism.
- [ ] Add versioned webhooks/notifications after durable execution events.

## Baseline verified 9 September 2026

- Frontend `npm run build`: passed. Bundle-size warnings remain.
- Fresh PostgreSQL `alembic upgrade head`: passed; one merged head.
- Full backend tests on a separately created, migrated and seeded database:
  **125 passed, 1 skipped**.
- The existing callback-idempotency test remains incomplete/skipped and must be
  replaced as part of execution repair. Passing this suite is not an end-to-end
  agent execution guarantee.

## Local verification

Use an isolated PostgreSQL test database, never a production database. Existing
integration tests require seeded admin data and some commit their changes.

From `backend/`, in a Python environment with PostgreSQL and Redis available:

```text
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m scripts.seed_admin
python -m pytest tests -q
```

Set `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD` and `REDIS_HOST` for that test environment. See `.env.example`
for other settings. The seed script creates a development account; do not use
that account in a public deployment.

From `frontend/`:

```text
npm ci
npm run build
```

The next acceptance milestone is a real locator-backed test with assertions
executed by the modern agent, with correlated results and browser-viewable
evidence. Do not close the project based on API/model presence alone.
