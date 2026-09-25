"""Require a complete CI run for the exact integration-branch source revision."""

import json
import os
import re
import subprocess


REQUIRED_STEPS = {
    "Backend Tests": {"Lint with Ruff", "Type check with ty", "Run tests with coverage"},
    "Frontend Checks": {"Lint", "Type check & Build", "Run tests"},
    "Migration Chain": {"Check the Alembic revision chain"},
    "Helm Checks": {"Lint Helm Chart", "Validate Helm Chart with Kubeconform"},
}


def matches_source(run, source_sha):
    return (
        run.get("head_sha") == source_sha
        and run.get("head_branch") == "codex/tensor"
        and run.get("event") in {"push", "workflow_dispatch"}
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    )


def complete_jobs(jobs):
    for name, required_steps in REQUIRED_STEPS.items():
        matching = [job for job in jobs if job.get("name") == name]
        if len(matching) != 1 or matching[0].get("conclusion") != "success":
            return False
        successful_steps = {
            step.get("name")
            for step in matching[0].get("steps", [])
            if step.get("conclusion") == "success"
        }
        if not required_steps <= successful_steps:
            return False
    return True


def api_pages(path, key):
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return [item for page in json.loads(result.stdout) for item in page[key]]


def find_complete_run(repo, source_sha, fetch=api_pages):
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Source must be a full lowercase 40-character commit SHA")
    runs = fetch(
        f"repos/{repo}/actions/workflows/ci.yml/runs?head_sha={source_sha}&per_page=100",
        "workflow_runs",
    )
    for run in runs:
        if matches_source(run, source_sha):
            jobs = fetch(
                f"repos/{repo}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100",
                "jobs",
            )
            if complete_jobs(jobs):
                return run["id"]
    raise ValueError("No complete successful integration-branch CI run for this exact SHA")


if __name__ == "__main__":
    run_id = find_complete_run(os.environ["GITHUB_REPOSITORY"], os.environ["SOURCE_SHA"])
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"ci_run_id={run_id}\n")
    print(f"Verified complete CI run {run_id}")
