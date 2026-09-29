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

## Product increment — 21 September 2026

Reviewed drafts can now promote to either a TestCase or a reusable Flow. Flow
promotion preserves locators, input placeholders, checksum, first authored
revision and draft provenance. Repeated promotion returns the same asset;
promotion to a different target is rejected. The UI opens the promoted flow.
Migration `e6f7a8b9c0d1` passed on a fresh database and the local database.
Verification: **174 passed, 1 skipped**, including browser and Celery integration;
frontend TypeScript and production build passed. The DPAPI skip remains.
Windows installation/pairing verification is deferred at the user's request.
BusinessAction promotion and parameterized composition remain next.

## BusinessAction increment — 21 September 2026

BusinessActions now have an explicit immutable asset kind in the canonical
reusable-asset table. They share FlowStep, Flow revisions and FLOW call expansion;
there is no second execution engine. Creation, draft promotion, duplication,
library labels and test-case selection preserve the distinction. Existing rows
remain FLOW. Migration `f7a8b9c0d1e2` adds the constrained kind column.
This is an initial reusable-action implementation: environment/run placeholders
work, but per-call input contracts, outputs and nesting are still outstanding.

## Delivery checklist

Current priority: complete the in-product testing loop before expanding feature
scope. See [PRODUCT_TESTING.md](PRODUCT_TESTING.md) for the new setup and usage
path. Agent enrollment, direct browser-to-draft upload, Run with environment/agent
selection, and fresh saved-case reruns are implemented. Migration
`d5e6f7a8b9c0` adds enrollment and recording state. Windows installation/pairing
under a normal interactive user remains an acceptance gate; the installer still
depends on preinstalled Python and Edge.

- [x] Repair the frontend production build against the locked Material UI version.
- [x] Merge Phase 4/5 migration branches without rewriting their history.
- [x] Declare scheduler runtime and development-test dependencies.
- [x] Execute Reports SQL on PostgreSQL; correct weekly buckets and duration weighting.
- [x] Add PostgreSQL report regressions and build/test CI.
- [ ] Establish reproducible dependency lockfiles for the supported backend runtime.
- [x] Preserve locators, assertions, timeouts, optionality and input resolution in snapshots.
- [x] Connect a modern authenticated browser agent to the HTTP poll/callback protocol.
- [x] Wire flow references through API/editor and preserve authored flow revisions.
- [ ] Enforce tenant-reference validation and mutation permissions consistently.
- [ ] Require safe secret configuration; prevent persisted plaintext run secrets.
- [ ] Repair lease renewal, capacity, terminal-state fencing, abort and retries.
- [ ] Make event allocation transactional; repair scheduler/offline-detector paths.
- [x] Connect lease-scoped PNG evidence upload and authenticated artifact viewing.
- [ ] Extend agent evidence to video, trace and HAR capture.
- [ ] Complete dashboard, queue, SSE resumption and report timezone handling.
- [x] Implement local recording → reviewed DraftAsset → TestCase promotion with provenance.
- [ ] Extend capture coverage and add BusinessAction/Flow promotion and approval workflow.
- [ ] Implement BusinessAction inputs/outputs and reusable composition.
- [ ] Implement global/environment/generated/secret datasets and manual outcomes.
- [ ] Implement execution profiles, suite runs, templates and bounded parallelism.
- [ ] Add versioned webhooks/notifications after durable execution events.

## Latest verification — 16 September 2026

- Full backend suite: **173 passed, 1 skipped**, on a fresh, migrated and seeded
  isolated PostgreSQL database, with browser and Celery integration tests enabled.
- Actual desktop capture, Stop/upload, draft promotion, assertion execution and
  repeat agent execution passed against a local browser fixture.
- The single skip is Windows DPAPI credential storage: the impersonated Codex
  sandbox has no loaded user profile. Normal-user installation and pairing remain
  required acceptance checks; no plaintext credential fallback was introduced.
- Frontend TypeScript check and production build passed. Existing bundle-size and
  dependency-deprecation warnings remain. The Windows installer passed syntax
  checking but has not been tested on a clean machine.

## Baseline verified 9 September 2026

- Frontend `npm run build`: passed. Bundle-size warnings remain.
- Fresh PostgreSQL `alembic upgrade head`: passed; one merged head.
- Full backend tests on a separately created, migrated and seeded database:
  **125 passed, 1 skipped**.
- That baseline included an incomplete/skipped callback-idempotency test. It has
  now been replaced by actual callback replay and fencing tests in
  `test_execution_contract.py`.

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

## Reusable flow milestone — 11 September 2026

Verified: **166 tests passed, none skipped**, including seven real-browser cases
and the separate Celery Beat/worker acceptance test. The frontend typecheck and
production build passed. Fresh and populated PostgreSQL migration checks passed;
the populated check preserved an existing revision 7 without inventing versions
1–6. The local database is migrated through `c4d5e6f7a8b9`.
Existing dependency deprecations and frontend bundle-size warnings remain.

Flow mutations now append authored revisions to the existing `asset_revisions`
store. A per-flow row lock serializes mutations, and a partial unique index
prevents duplicate revision numbers. Migration `c4d5e6f7a8b9` preserves the
current content of existing live flows. Older overwritten versions cannot be
reconstructed and remain unavailable.

In the test-case editor, add a step, select `FLOW`, choose a reusable flow and
its pinned revision, then save. Flow edits do not automatically upgrade that
reference. Revision list/detail endpoints expose the preserved history.
Execution expands the pinned authored steps, with distinct execution IDs for
each invocation. Flow mutations require TESTER or higher; references and page
objects are checked against the organization.

This is authored flow versioning: page-object locators remain independently
editable and are resolved and frozen when each run is queued. Flow step
timeouts and optionality apply individually. Flow-reference assertions,
wrapper action settings and nested flows are rejected. Empty revisions cannot
run. Deleting a flow prevents new runs that reference it, while retained
revisions and already queued snapshots remain intact.

Remaining foundations: secret-storage hardening, consistent tenant checks
across other authoring APIs, and broader asset revision coverage. Next reusable
authoring work is DraftAsset → Flow promotion and BusinessAction parameters;
the current recorder still promotes to TestCase only.

## Recording pilot milestone

Verified 10 September: 156 tests passed, none skipped; frontend production build
and fresh PostgreSQL migrations passed. A real-browser test records text/password
interactions, imports a draft, promotes it to a test case, adds an assertion and
replays the case through the HTTP agent. Password values are replaced by variable
references before export; the replay test uses an environment secret and verifies
that its value is absent from the execution snapshot.

Use [the recording pilot guide](execution_agent/RECORDING.md). The first workflow
uses a local recording file imported under Test Cases → Recording drafts. Users
review/edit values and locators, choose an existing repository page, then promote.
Draft edits use optimistic versions; promotion is transactional and idempotent.
Assertions are authored after promotion. BusinessAction/Flow promotion, broader
capture coverage and secret-storage hardening remain. Authored flow revisions
were added in the subsequent milestone above.
Migration `b3c4d5e6f7a8` adds draft storage; apply migrations before restarting.

## Modern execution milestone

Orchestration follow-up (10 September): retries preserve step counts and variable
provenance, automatic retry eligibility is persisted in `available_after`, and
agent polling excludes retries still in backoff. Failed callbacks apply the
configured retry policy, with replay protection. Watchdog events use the same
serialized sequence allocator as callbacks; requeue no longer counts as another
dispatch. Migration `f0a1b2c3d4e5` adds the nullable availability timestamp.
Run `python -m alembic upgrade head` before restarting the updated backend.
Periodic Beat delivery and server-enforced deadlines are now acceptance-tested.
Deadline follow-up: `a2b3c4d5e6f7` adds `deadline_at`, backfilling existing started
runs. The first RUNNING callback fixes the deadline; renewals cannot extend it.
Late callbacks/uploads are rejected. The watchdog distinguishes deadline expiry
(TIMED_OUT, timeout retry policy) from a lost agent (ABORTED).
The broker acceptance test now launches Beat as well as a worker and checks
periodic watchdog/offline delivery and deadline enforcement with a live lease.
Apply migrations before restarting the updated backend.
Verification: 150 tests passed, none skipped, including separate Beat/worker
processes using Redis, real browser execution and fresh PostgreSQL migrations.
The Beat acceptance test shortens intervals and isolates its queue; it does not
replace production soak testing or scheduler crash-recovery verification.
Follow-up: removed the unused alternate recovery implementation, leaving the
scheduled watchdog as the single lease-recovery path. Fixed offline detection's
unsupported audit argument and locked stale-agent selection against concurrent
detectors. Redis client dependency is constrained to the compatible 5.x line;
install updated requirements when upgrading an existing environment.
`RUN_CELERY_TESTS=1` enables a separate-process worker test through Redis, using
a unique queue and the isolated PostgreSQL test database. CI enables this test.
Verified follow-up: 149 tests passed, none skipped, including real browser tests
and a separate Celery worker processing health, watchdog and offline tasks over
local Redis. Worker shutdown and queue cleanup are part of the acceptance test.
Verification: 147 tests passed, none skipped, including the real-browser tests;
fresh PostgreSQL migration through the new head passed.

Verified 9 September 2026: **145 backend tests passed, none skipped**, including
five real Edge browser tests. Fresh PostgreSQL migrations and the frontend
production build passed. Existing dependency-deprecation and bundle-size
warnings remain. GitHub CI is configured for Chromium; its remote run has not
been observed locally.

The canonical agent is now `execution_agent/`; see its [setup and protocol
documentation](execution_agent/README.md). Snapshot version 2 freezes the authored
execution contract. Agent results are checked against those frozen identities,
terminal callbacks are fenced, and callback event allocation is serialized.
Operator mutations require TESTER or higher. Active callbacks renew leases,
and agent claims are checked against registered capacity.

Real browser acceptance covers locator fallback, assertions, correlated results
and authenticated PNG evidence. These tests use a local webpage and the
FastAPI ASGI HTTP transport, backed by PostgreSQL. They do not establish that
the Celery/watchdog/retry deployment is production-ready.

Next development order:

1. Consolidate watchdog/event writers; repair retry delay, automatic retry
   triggers and timeout/abort behavior across scheduler and worker processes.
   Resolve the local Redis client/server compatibility issue and verify this
   lifecycle with real background workers.
2. Enforce safe secret configuration and tenant-reference validation at every
   authoring boundary; extend revision coverage beyond authored flows.
   Flow references now use preserved revisions in the API/editor.
3. Implement recorder → DraftAsset review → governed promotion, followed by
   BusinessAction parameters and composition.
4. Add datasets/manual outcomes, execution profiles, suites/templates and
   bounded parallel execution. Expand evidence capture and operator views.

Do not close the project based on API/model presence alone.
