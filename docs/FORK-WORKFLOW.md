# Fork workflow

This public fork contains application source and generic development guidance.
Deployment configuration is versioned separately in a private repository. Neither
repository stores secrets, bank data or backups. This setup does not change the
running application.

## Branches and provenance

- `origin` is this fork; `upstream` is `securo-finance/securo`.
- `main` tracks upstream and does not receive personal customizations.
- `codex/tensor` is the default integration branch. Its initial application base is
  tag `v0.16.1`, commit `30db776cd294b6ae6f9a627ec4b84053c6c2c743`.
- Create focused `codex/<topic>` branches from the current integration branch and
  target their PRs at `codex/tensor`. Inspect Git status before switching branches.
- Preserve history: no force pushes or resets of shared branches. A versioned
  source change is not proof of which image is deployed; deployment records must
  identify both the source revision and immutable image digest.

## Changes and upstream updates

Classify each PR as configuration, upstream candidate or personal customization.
Keep generic changes independent of private configuration and personal data.

For an update, fetch upstream refs, review the chosen release and migrations,
and propose a merge into `codex/tensor` on a separate `codex/` update branch.
Resolve conflicts against the current architecture, run appropriate checks and
record the upstream revision. Do not automatically upgrade the deployed service.
Backup, restore readiness, image publication and deployment belong to a separate
release task with its own verification.

For an upstream contribution, start a separate branch from current `upstream/main`
and transfer only the focused generic commits. Follow `CONTRIBUTING.md`: discuss
new features or core changes with maintainers before offering implementation.
Search existing issues before proposing a new one. Keep private work-ledger
content out of public issues and PRs. When upstream merges an equivalent change,
remove the superseded fork-specific implementation during a reviewed update.

## CI and publication

The audited `CI` workflow checks pushes and PRs targeting `main` or `codex/tensor`
and supports manual dispatch. Its GitHub token has `contents: read`; it does not
publish images or deploy. Fork CI omits upstream coverage-badge extraction and
publication; no badge credential is needed. Repository Actions uses a selected
allowlist matching the audited CI action references:

- `actions/checkout@v7`
- `actions/setup-python@v7`
- `actions/upload-artifact@v7`
- `actions/setup-node@v7`
- `azure/setup-helm@v5`

Review any action-version change and update that allowlist explicitly before
running the changed workflow.

Initially enable only `ci.yml`. Leave `release.yml`, `prepare-release.yml`,
`downloads-badge.yml`, `pr-labels.yml` and `label-guard.yml` disabled in the fork.
Every job in those five workflows is guarded to run only in the original
`securo-finance/securo` repository. These guards prevent publication and other
mutations if Actions must be enabled globally before GitHub registers the
workflows and permits disabling them individually. Push the guarded definitions
while Actions is disabled, enable Actions to register them, then disable all five
workflows individually and verify that only CI is active. Keep the guards even
after disabling the workflows as protection against accidental re-enablement.
Recheck both guards and enabled state after upstream updates introduce or change
workflows. Do not create release credentials or publish releases merely to
validate repository setup.

CI preserves the selected baseline's backend, frontend, migration-chain and Helm
checks. A documentation-only PR may skip the backend and Helm suites, while
pushes and manual dispatch run them. Read the job results rather than treating
an overall workflow status as evidence that every suite executed.
