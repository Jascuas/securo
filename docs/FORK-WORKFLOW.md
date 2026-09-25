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

Enable `ci.yml` and the manually dispatched `fork-release.yml`. Leave `release.yml`, `prepare-release.yml`,
`downloads-badge.yml`, `pr-labels.yml` and `label-guard.yml` disabled in the fork.
Every job in those five workflows is guarded to run only in the original
`securo-finance/securo` repository. These guards prevent publication and other
mutations if Actions must be enabled globally before GitHub registers the
workflows and permits disabling them individually. Push the guarded definitions
while Actions is disabled, enable Actions to register them, then disable all five
workflows individually and verify that only CI and Publish Fork Images are active. Keep the guards even
after disabling the workflows as protection against accidental re-enablement.
Recheck both guards and enabled state after upstream updates introduce or change
workflows. Do not create release credentials or publish releases merely to
validate repository setup.

CI preserves the selected baseline's backend, frontend, migration-chain and Helm
checks. A documentation-only PR may skip the backend and Helm suites, while
pushes and manual dispatch run them. Read the job results rather than treating
an overall workflow status as evidence that every suite executed.


## Publishing a candidate

`Publish Fork Images` (`fork-release.yml`) is manually dispatched from
`codex/tensor`. It never deploys or connects to a server. Give it a full lowercase
40-character source commit SHA reachable from that branch. The gate requires a
successful `CI` push or manual run for that exact commit on `codex/tensor`, checks
all four application jobs, and verifies their real test/lint steps succeeded.
A successful PR run with skipped suites cannot authorize publication. Release
admission tests also run in CI's `Release Policy` job.

```sh
# Run these against this fork, after the source PR has merged.
gh workflow run ci.yml --ref codex/tensor
# Wait for the complete CI run at the chosen SHA, then publish explicitly.
gh workflow run fork-release.yml --ref codex/tensor -f source_sha=<full-commit-sha>
```

The build publishes `linux/amd64` backend and frontend images to
`ghcr.io/jascuas/securo-backend` and `ghcr.io/jascuas/securo-frontend`. Each attempt
uses `sha-<full-sha>-run-<run-id>-<attempt>`; it never publishes `latest` or moves
an integration tag. OCI labels identify the source repository, source revision
and unique image version. The frontend displays `fork-<full-sha>` through the
existing `VITE_APP_VERSION` build argument. No bank or deployment credentials
are available to this workflow. Only the publishing job gets `packages: write`;
the source gate gets `actions: read`, and both get `contents: read`.

Both images must publish before the workflow produces `release-manifest.json`
in the `release-manifest-<run-id>-<attempt>` artifact (retained for 90 days). It
records schema version 1, source repository/SHA, platform, unique tag, backend
and frontend immutable digest references, CI/build run URLs and build attempt.
Copy the reviewed manifest into the private operations repository when selecting
a candidate; artifacts alone are not permanent deployment records. GHCR package
visibility is managed separately from repository visibility: verify intended
pull access before deployment. An interrupted build may leave one published
image; without a complete manifest and successful workflow it is not a complete
candidate. Retry produces a new attempt tag.

The release workflow pins its actions to these reviewed immutable references;
add them explicitly to the repository's selected action allowlist:

- `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (v7)
- `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` (v7)
- `docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069` (v4)
- `docker/login-action@dbcb813823bdd20940b903addbd779551569679f` (v4)
- `docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc` (v7)

Builds retain upstream Dockerfiles and their base-image tags. A source SHA alone
does not guarantee identical rebuilt bytes; record the produced digests and use
those exact digests for deployment. Building images verifies neither production
migration behavior nor financial imports. Before deploying any candidate, the
private deployment procedure must require a recoverable encrypted backup,
isolated restore evidence, migration assessment and explicit release selection.
Merging source or publishing images changes no running service.

To check the release gate locally without credentials:

```sh
python3 -m unittest discover -s .github/scripts -p 'test_release_gate.py' -v
```
