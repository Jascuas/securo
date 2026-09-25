"""Offline boundary tests for release admission; no provider or production access."""

import unittest

from release_gate import REQUIRED_STEPS, complete_jobs, find_complete_run, matches_source

SHA = "a" * 40


def successful_run(**changes):
    return {
        "id": 17,
        "run_attempt": 2,
        "head_sha": SHA,
        "head_branch": "codex/tensor",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        **changes,
    }


def successful_jobs():
    return [
        {
            "name": name,
            "conclusion": "success",
            "steps": [{"name": step, "conclusion": "success"} for step in steps],
        }
        for name, steps in REQUIRED_STEPS.items()
    ]


class ReleaseGateTests(unittest.TestCase):
    def test_only_complete_exact_integration_runs(self):
        self.assertTrue(matches_source(successful_run(), SHA))
        self.assertTrue(matches_source(successful_run(event="workflow_dispatch"), SHA))
        for change in [
            {"head_sha": "b" * 40}, {"head_branch": "main"},
            {"event": "pull_request"}, {"status": "in_progress"},
            {"conclusion": "failure"}, {"conclusion": "cancelled"},
        ]:
            with self.subTest(change=change):
                self.assertFalse(matches_source(successful_run(**change), SHA))

    def test_missing_duplicate_failed_jobs_and_skipped_steps_rejected(self):
        self.assertTrue(complete_jobs(successful_jobs()))
        self.assertFalse(complete_jobs(successful_jobs()[1:]))
        self.assertFalse(complete_jobs(successful_jobs() + successful_jobs()[:1]))
        for index in range(4):
            jobs = successful_jobs()
            jobs[index]["conclusion"] = "skipped"
            self.assertFalse(complete_jobs(jobs))
            jobs = successful_jobs()
            jobs[index]["steps"][0]["conclusion"] = "skipped"
            self.assertFalse(complete_jobs(jobs))

    def test_uses_exact_successful_attempt_and_skips_incomplete_runs(self):
        calls = []

        def fetch(path, key):
            calls.append(path)
            if key == "workflow_runs":
                return [successful_run(id=16), successful_run()]
            return [] if "/runs/16/" in path else successful_jobs()

        self.assertEqual(find_complete_run("owner/repo", SHA, fetch), 17)
        self.assertIn("/attempts/2/jobs", calls[-1])

    def test_fails_closed_without_evidence(self):
        with self.assertRaises(ValueError):
            find_complete_run("owner/repo", SHA, lambda *_: [])
        for invalid in ["main", "a" * 7, "A" * 40, "a" * 40 + "\n"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                find_complete_run("owner/repo", invalid, lambda *_: self.fail("API called"))


if __name__ == "__main__":
    unittest.main()
