# Agent instructions

## Purpose and authority

This is a public fork of Securo, a personal-finance application. Preserve its
architecture and upstream compatibility; implement small, focused changes.
`CONTRIBUTING.md`, `SECURITY.md`, the license, current source and this file govern
work here. `docs/FORK-WORKFLOW.md` explains fork branches and contribution flow.
Dated analysis documents are evidence and proposals, not permission to implement
features or change the deployed service.

Read the complete Git status before editing and preserve unrelated work. Do not
copy architecture rules from a different application into Securo. Existing code
is the starting point, not proof that every behavior is correct. Verify claims
against the selected revision and distinguish findings from recommendations.

## Architecture and placement

- `backend/app/api/` owns FastAPI HTTP adapters and boundary validation. Reuse
  authentication, workspace access and dependency patterns from nearby endpoints.
- `backend/app/services/` owns domain operations, SQLAlchemy persistence and
  transaction coordination. Extend the owning service rather than introducing a
  parallel persistence or domain layer.
- `backend/app/models/` owns persistent models; `backend/app/schemas/` owns
  Pydantic request and response contracts. `backend/alembic/versions/` contains
  reviewed schema migrations, chained to the selected branch's current head.
- `backend/app/providers/` translates external bank payloads into provider
  contracts; `backend/app/tasks/` owns background tasks. Keep provider-specific
  quirks at the adapter boundary and reuse existing sync orchestration.
- `backend/app/agents/` owns optional AI runtime, provider adapters and agent
  configuration. `backend/mcp_server/` exposes tools over existing domain services.
  Reuse these capabilities; do not add a second AI stack for categorization.
- `frontend/src/pages/` composes routes; reusable UI belongs in existing
  components. Use `frontend/src/lib/api.ts` and established React Query patterns
  for server state. Reuse current UI primitives, translations and test helpers.
- Follow the owning module's naming and import conventions. Extract abstractions
  when they hide real complexity or serve existing callers, not hypothetical use.

## Financial and authorization invariants

- Authentication is not ownership. Validate the current workspace, permissions
  and every referenced account, category, transaction or other entity through
  the existing domain checks. Preserve intentional sharing behavior.
- Monetary values use the existing Decimal/Numeric conventions, currencies and
  debit/credit transaction semantics. Do not import another application's
  milliunit encoding or invent a sign convention. Inspect the relevant account,
  transfer, split and balance services before changing financial calculations.
- Preserve provider external IDs, sync deduplication, pending/posted handling,
  repeat-import behavior and manual edits. Test repeated sync or import when
  changing these paths. Do not repair real records as a side effect of code work.
- Extend `rule_service` and the pure `rule_engine` for rule behavior. Before
  changing categorization, trace existing rule precedence, overwrite settings,
  explicit user choices, import and bank-sync call sites.
- Validate AI output against categories and entities visible in the workspace.
  Suggestions do not authorize writes. Preserve Securo's proposal and user Apply
  flow; mutations use the existing authorized service/API path.
- Financial amounts, dates, transaction identity and balances remain owned by
  deterministic domain logic. An AI suggestion must not silently alter them.
- Report partial import, sync or AI failures explicitly. Do not turn unexpected
  infrastructure errors into success or empty data. Keep logs useful without
  raw bank payloads, personal financial descriptions, credentials or tokens.

## Public-source and tooling boundaries

This repository must contain no production secrets, private deployment addresses,
real bank statements, personal categorization examples, database dumps or backups.
Use synthetic fixtures. Deployment-specific configuration belongs in the separate
private deployment repository; secrets remain outside both repositories.
Never print secret values or read credential files merely to discover settings.

The shared private work ledger is the Plane project **Securo**, prefix **SEC**.
Use the installed `plane-work-management` skill for work-item procedures and
available GitHub/Plane MCP tools for integration. Discover identifiers, states,
permissions and tool capabilities live; do not embed account-specific IDs,
credentials or mutable task status here. Read the exact target before an
external mutation and stay within the user's authorized task scope. Do not
publish private Plane ticket text or financial details in public PRs.

Development tools are distinct from Securo's financial MCP. Do not enable the
optional financial MCP, mint its tokens or connect it to a development agent as
part of repository setup. External Securo MCP callers can apply mutations;
its proposal tools are not a guarantee of read-only access.

## Work and contribution flow

Classify each change in its PR description as **configuration**, **upstream
candidate**, or **personal customization**. Favor configuration and existing
extension points before application patches. Use focused `codex/` branches and
Conventional Commit messages; do not commit or push unrelated files.

The integration branch is `codex/tensor`; `main` follows upstream. An application
PR does not deploy the application. Upstream updates, image publication,
migrations, deployment and live data changes are separate operations. Preserve
license and attribution, and follow upstream's advance discussion requirement
for new features and core changes before offering that work upstream.

Implementers run their own relevant automated checks. The user performs browser
acceptance using a concise checklist supplied with user-facing changes. Do not
create separate test or review agents. Parallel implementers must own disjoint
files and coordinate through the orchestrator.

## Verification

Use the commands from the checked-out revision, not commands borrowed from other
projects. Backend dependencies are locked with uv; frontend dependencies use npm.

```sh
# From backend/; install the locked development environment once.
uv sync --locked --all-extras
uv run --no-sync ruff check .
uv run --no-sync ty check .
uv run --no-sync pytest -n auto --dist loadfile --cov=app --cov-report=term-missing --cov-fail-under=60 -ra -W error

# From the repository root; validate migrations without applying them.
python3 backend/scripts/check_migration_chain.py

# From frontend/; npm configuration disables dependency install scripts.
npm ci
npm run lint -- --max-warnings=0
npm run build
npm test
```

- Documentation-only changes: run `git diff --check` and verify referenced paths,
  commands and architectural claims. Do not add tests that mirror documentation.
- Backend changes: run Ruff, ty and relevant tests; use the full backend CI suite
  for cross-cutting changes. The v0.16.1 test harness uses synthetic credentials
  and SQLite fixtures; those checks do not prove production PostgreSQL behavior.
- Frontend changes: run lint, tests and build; build includes type checking.
  Add meaningful behavioral tests and update EN/PT-BR strings for changed UI.
- Schema changes: review generated migration SQL and validate the revision chain.
  Do not apply migrations or point tests at live data without explicit scope.
- Chart changes: preserve CI's Helm lint and rendered-chart validation checks.
- Workflow changes: validate syntax, event/branch filters, permissions and enabled
  workflows, then inspect the real CI run. Never confuse a skipped check with a
  passing test suite.

Report exactly which checks ran, failures and untested behavior. For browser
changes, provide the user with short steps covering the affected flow, failure
states, keyboard operation and the relevant responsive layout. A passing test
suite does not establish correctness of a live financial import.
