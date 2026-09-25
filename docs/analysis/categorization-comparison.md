# Categorization: Securo and Aureo

Dated source review: 2026-09-25. Status: proposal for discussion; no categorization code, provider activation, bank operation or deployment performed.

## Recommendation

Build a bounded, user-triggered **Suggest categories** flow for existing uncategorized transactions, extending Securo's existing proposal review, providers and domain services. Adapt Aureo's useful behavior—history-first suggestions, category allowlists and editable review—without transplanting its CSV workflow, authentication, storage or TypeScript provider implementation.

Start with review and explicit Apply. Do not automatically categorize on bank sync in the first release. Categorization must neither change amounts nor create, merge or delete transactions. Historical import is a separate feature.

## Evidence and limits

| Source | Inspected revision | Scope |
|---|---|---|
| Securo deployed-source baseline | `30db776cd294b6ae6f9a627ec4b84053c6c2c743` (`v0.16.1`) | Rules, sync/import integration, transaction updates, agents, providers, proposals and review UI |
| Securo upstream snapshot | `3b684e1ece168dbd5eea30145881ac84250a39ef` (`upstream/main` when inspected) | Differences against the baseline in those same areas |
| Aureo source | `afd7c20e9b6abc37a4a1200a1f3357d374f48110` | CSV analysis service, provider interfaces/prompts, confidence review and manual corrections |

Aureo had untracked analysis documents; inspected implementation files were unchanged relative to that commit. Aureo references below are repository-relative source pointers, not public repository links. This is static source evidence, not evidence that any AI connection is enabled or that categorization accuracy has been measured. No private data or credentials were read for this report. Examples below are synthetic.

### Securo source map

All baseline links pin the exact inspected revision:

- [Proposal tool](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/mcp_server/tools/proposals.py): `propose_categorize`, `_can_apply`.
- [Review card](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/frontend/src/components/agents/proposal-card.tsx): `ProposalCard`, `applyProposal`.
- [Transaction service](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/services/transaction_service.py): `_ensure_category_in_workspace`, `bulk_update_category`; [HTTP adapter](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/api/transactions.py): `bulk_categorize`.
- [Rule service](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/services/rule_service.py): `preview_rules_for_transaction`, `apply_rules_to_transaction`; [engine](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/services/rule_engine.py): `apply_rule_actions`.
- [Import service](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/services/import_service.py): `enrich_with_category_suggestions`; [sync service](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/services/connection_service.py): `_find_installment_category`, `_match_pluggy_category`, rule application on incoming transactions.
- [Providers](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/agents/providers/registry.py), [executor](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/agents/runtime/executor.py), [usage](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/agents/services/usage_service.py) and [context primer](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/agents/services/context_service.py).
- [Transaction reads](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/mcp_server/tools/transactions.py), [agent settings](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/agents/config.py), [conversation storage](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/agents/models/conversation.py), [connection service](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/agents/services/connection_service.py) and [transaction model](https://github.com/securo-finance/securo/blob/30db776cd294b6ae6f9a627ec4b84053c6c2c743/backend/app/models/transaction.py).

### Aureo source map

At the Aureo revision above:

- `features/csv-import/server/csv-import-analysis-operations.ts`: `findPayeeRows`, `findFewShotRows`, `createAICategorizations`, `categorizeInBatches`, `analyzeCsvImport`.
- `features/csv-import/lib/config.ts`: match thresholds, batch bounds and example limits.
- `lib/ai/types.ts`, `lib/ai/prompts.ts`, `lib/ai/index.ts`, `lib/ai/gemini-provider.ts`, `lib/ai/openrouter-provider.ts`: provider contracts, prompt data and output parsing.
- `features/csv-import/hooks/use-import-orchestrator.ts`: `handleCategoryChange`; `features/csv-import/components/ai-import-steps/review-step.tsx` and `confidence-badge.tsx`: editable review.
- `features/csv-import/server/csv-import-write-operations.ts`: ownership validation on import; `csv-import-analysis-operations.test.ts`: invalid-category and history-resolution regression cases.

## Current behavior and gaps

| Capability | Securo baseline | Aureo | Decision |
|---|---|---|---|
| Deterministic rules | Active rules ordered by priority and ID; detached preview available. Category actions preserve an already-set category and skip hidden categories. Incoming sync and imports invoke rules. | CSV analysis uses historical merchant matching rather than the same rule engine. | **Reuse** Securo rules and preview; do not introduce a competing rules engine. |
| Merchant/history evidence | MCP transactions support payee/search filters. Sync reuses categories from earlier matching installments. Reviewed code has no equivalent general merchant vote-share categorizer. | Case-insensitive exact payee matches, then PostgreSQL trigram fuzzy matches. Category/type vote share and at least two matches can resolve a row before AI. | **Adapt** bounded, workspace-scoped history hints. Start with exact payee evidence; defer fuzzy auto-resolution. |
| AI proposals | Chat agent can read transactions and propose assigning one category to multiple transactions. UI Apply calls the existing bulk categorization API. | CSV rows receive individual suggestions before import. | **Reuse and extend** Securo's proposal family for mixed-category batch review. |
| Confidence | Categorization proposal has no row-level confidence or history-source contract. | Numeric model confidence and historical vote share drive preview values; UI shows percentages. | **Adapt** evidence labels and model confidence, clearly distinguished. Neither number is calibrated correctness probability. |
| Manual correction | Ordinary categorization updates exist. Rule application preserves populated categories. Bulk categorization intentionally overwrites selected rows. | Preview category edits set client `userEdited`; import checks owned categories. | **Adapt** editable preview; preserve changes made after generation using server revalidation. Do not equate the client flag with durable learning provenance. |
| Providers | Registry supports OpenAI, Anthropic, Ollama and OpenAI-compatible connections; connection keys are encrypted in storage. | Gemini and OpenRouter implementations; `claude` is declared but throws as unimplemented. | **Reuse** Securo adapters. Investigate desired model through an existing adapter before adding a provider. |
| CSV | CSV parser, deterministic suggestions and import already exist. | AI-assisted CSV mapping, duplicate analysis and categorization are closely coordinated. | **Defer** enhanced CSV work; bank-synced existing rows are the first categorization target. |
| Money and identity | Decimal `Numeric(15,2)` transaction amounts, credit/debit type, workspace IDs and existing transaction UUIDs. | Integer milliunits, user-scoped data and transient CSV row indices. | **Keep** Securo's representation and transaction identity. No conversion or duplicate detection in categorization. |

### Review integrity needs an explicit extension

The existing proposal is useful infrastructure, but it is not a durable categorization approval protocol:

- `propose_categorize` validates the category and resolves transaction IDs inside a workspace. It reports `missing_ids`, but the current frontend proposal type/card does not make that a per-row outcome contract.
- Browser Apply calls `PATCH /api/transactions/bulk-categorize`. The proposal's advisory `apply_endpoint` string names a different route; use the actual typed client and HTTP adapter as the integration source of truth.
- `bulk_update_category` validates category workspace and scopes transaction writes, but does not compare the row with its preview state. A manual edit between suggestion and Apply can be overwritten.
- Applied-card state is stored in browser `localStorage`; it is not a server receipt. The card reports success from the returned count without reconciling it against every proposed row.
- Built-in chat proposals are previews. External MCP callers can request `apply=true`; do not assume every caller of a `propose_*` tool is incapable of writing.

These findings identify requirements for the future batch feature, not authorization to change existing API behavior in this phase.

### Privacy, cost and failure behavior

Securo already records token usage and estimated cost. Its hardcoded price table is approximate, and unknown provider/model combinations return no cost estimate. That is not a spending limit. The chat executor bounds tool iterations and history, while transaction reads cap pages at 50 rows. Reusing an unconstrained conversation as a bulk classifier would still incur variable tool and context costs.

The optional context primer includes identity and account information; tool results and conversations can be persisted. A focused categorization request should send only merchant/description, permitted category labels and a small set of relevant history examples. Exclude identity, balances, account numbers and free-text notes by default. Treat transaction descriptions as untrusted data, never instructions. A local model is an available adapter option, not proof that all configured processing is local.

Aureo avoids AI for sufficiently consistent history, caps examples at 20 and sends unresolved rows in batches of 30, with up to three concurrent calls. Non-rate-limit failures receive bounded retries; a failed batch rejects the overall analysis through `Promise.all`. Successfully completed sibling calls may still have incurred cost. Its provider output uses JSON parsing and TypeScript assertions; the analysis service constrains category IDs, but this is not a complete runtime schema validator for every model field. Reuse these ideas with stricter typed validation and explicit partial results, not the implementation unchanged.

### Upstream differences checked

At upstream `3b684e1ece168dbd5eea30145881ac84250a39ef`, compared with the baseline:

- Categorization proposal logic, proposal card and `bulk_update_category` behavior are unchanged in the reviewed diff.
- Rules add transaction-status conditions; transaction listing improves transfer filtering.
- Agent context uses the application clock; the Anthropic adapter removes the temperature request parameter.
- CSV parsing improves amount/type handling and import duplicate identity. These are separate from batch categorization.

Updating alone does not supply the proposed history-first batch review feature. Recheck upstream immediately before implementation and discuss the feature before preparing a contribution.

## Smallest useful feature proposal

**Entry point:** an explicit action on selected, uncategorized, posted transactions in the active writable workspace. Default to excluding transfers. No background categorization and no changes to bank synchronization.

**Suggested first-release bounds:** at most 30 selected rows per request, processed as one bounded suggestion batch; up to 20 relevant historical examples. These are proposed defaults for product discussion, not changes made by this report.

1. Load and authorize the selected rows server-side. Preview existing rules first, without persistence. For unresolved rows, use exact payee history in the same workspace and transaction direction; ambiguous history stays unresolved. Preserve source labels such as rule, history or model.
2. Call the user's existing Securo AI connection only for the remainder. Validate a structured result: one known transaction ID at most once, an available category or null, bounded confidence when supplied, and no invented IDs. Do not train a model or create categories automatically.
3. Extend Securo's proposal review with an editable row list. Show suggestions, their evidence source and unresolved/failed rows. All rows remain unchanged until the user selects and applies them. A model failure must leave deterministic suggestions reviewable and the failed rows visibly unresolved.
4. Apply selected assignments through the transaction domain service with workspace/category validation and an atomic precondition that the transaction is still eligible and unchanged since preview. Return explicit updated, already-applied, skipped and conflicting outcomes. Do not silently overwrite later manual edits or claim a partial apply was complete.
5. Treat the next user correction as current history for later suggestions. Do not claim that historical categories are all manually confirmed: the existing model does not establish that provenance. Offer creation of an explicit merchant rule as a separate confirmation step, never silently.

**Interface impact to design in the implementation ticket:** a typed batch-suggestion result in the existing proposal family, row-level edit/selection state, and a guarded multi-category apply operation. Preserve existing categorization callers. The apply guard must include the previewed category and relevant transaction state/version, checked in the same transaction as the write. A category-only comparison cannot detect a description edit while the category remains null. Confirm the available version mechanism when designing the implementation; if a durable version or receipt requires schema changes, isolate and review its migration before deployment.

No database migration, API addition or runtime toggle is performed in this foundation phase. Provider activation and any internal financial MCP service required by the chosen runtime are a later deployment dependency, distinct from developer GitHub/Plane MCP tools.

## Proposed follow-up work

These are ticket proposals, not claims of implemented behavior or upstream acceptance.

| Work item | Acceptance outcome | Dependency / classification |
|---|---|---|
| Agree categorization UX and provider boundary | Approve bounded selection, review flow, history provenance, data sent to AI and model choice | This comparison; upstream candidate |
| Guard categorization Apply against stale previews | Atomic authorization and stale-state checks, explicit row outcomes, safe replay and regression tests | Agreed contract; upstream candidate |
| Generate bounded history-first suggestions | Rules/exact history before model, runtime output validation and visible partial failures | Agreed provider boundary; upstream candidate |
| Extend proposal review for category batches | Editable suggestions, selection, unresolved rows, conflict feedback and correct query refresh | Generation and guarded Apply; upstream candidate |
| Evaluate with synthetic examples | Accuracy, abstention and token usage reported without presenting model confidence as calibrated | Feature implementation; upstream candidate |
| Configure personal categories and merchant rules | User-approved categories/rules configured through existing interfaces | Private requirements; configuration |

Backup/restore readiness and a tested release image remain deployment prerequisites. Historical import, fuzzy history ranking, unattended classification, Gemini-specific adapters, broad UI redesign and migration from Aureo remain separate work.

## Synthetic acceptance scenarios

- Two posted debits from **Cedar Market** consistently categorized as Groceries suggest Groceries for a new matching debit; evidence says history. No AI request is needed when the deterministic policy resolves it.
- **Cedar Market** split across two conflicting categories remains reviewable and does not silently inherit a majority guess. A credit/refund is not inferred from debit-only history.
- A matching active rule produces a preview without a write. Hidden/deleted categories and categories from another workspace cannot be suggested or applied.
- A model returns an unknown ID, duplicate row, out-of-range confidence or malformed JSON: reject invalid output explicitly, preserve valid deterministic results and do not mutate transactions.
- A provider times out or rate-limits: show affected rows and retry scope; no false completion and no automatic resend of already accepted assignments.
- A transaction is manually categorized, edited, deleted or moved out of scope after preview: Apply reports conflict/skip and preserves current data. Two simultaneous Apply requests cannot overwrite one another's later corrections.
- A batch includes inaccessible transaction IDs: no data disclosure and no cross-workspace write. The result accounts for every requested row without exposing foreign details.
- Reopening a conversation on another browser does not rely on localStorage as proof of server application. Retrying a confirmed batch has no additional financial effect.
- Selection excludes pending transactions/transfers by default, stays within the configured bound and sends no notes/account metadata by default.
- Keyboard-only review permits category editing, row selection and Apply. Error and confidence labels work without color; applying refreshes the affected transaction views.

## Upstream discussion draft — not posted

**Title:** Reviewed batch category suggestions using rules and transaction history

Securo already supports categorization proposals, rule previews and explicit Apply. Would maintainers welcome a bounded action for selected uncategorized transactions that suggests categories using existing rules and workspace history, then the configured AI provider for unresolved rows?

The proposed flow reuses provider connections and proposal UI, lets users edit/select suggestions, and requires explicit Apply. It would add server-side protection against transaction changes between preview and Apply, and report partial/invalid model results clearly. It would not categorize automatically during sync, create categories, alter amounts, or add a second AI framework.

I would propose agreeing the review contract and stale-apply behavior first, followed by small implementation PRs with synthetic authorization, conflict and provider-failure cases. Is this direction compatible with the roadmap, and is there existing work we should build on?

## Verification performed

Inspected the listed source files and exact revision diff; checked the resulting document with `git diff --check` and validated referenced source paths against those revisions. No application tests or provider calls were run for this documentation-only comparison. Future acceptance scenarios are specifications, not passed tests.
