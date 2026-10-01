"""Synthetic receipt reconciliation without credentials or private network access."""
import unittest
from release_client import endpoint, publication_identity, release

REQUEST = {'app': 'test', 'operation_id': 'fixed-id', 'source_sha': 'a' * 40,
           'build_run_id': 100, 'build_run_attempt': 1, 'config_sha256': 'b' * 64}


class Fixture:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def call(self, method, operation=None, body=None):
        self.calls.append((method, operation, body))
        return next(self.responses)


class ClientTests(unittest.TestCase):
    def test_publication_waits_for_success_and_refuses_foreign_or_failed_run(self):
        run = {'head_repository': {'full_name': 'Jascuas/securo'}, 'head_branch': 'codex/tensor',
               'head_sha': REQUEST['source_sha'], 'path': '.github/workflows/fork-release.yml',
               'event': 'workflow_dispatch', 'run_attempt': 1, 'status': 'in_progress'}
        self.assertFalse(publication_identity(run, REQUEST))
        self.assertTrue(publication_identity({**run, 'status': 'completed', 'conclusion': 'success'}, REQUEST))
        for changes in ({'head_sha': 'f' * 40}, {'event': 'pull_request'}, {'run_attempt': 2},
                        {'head_repository': {'full_name': 'other/securo'}},
                        {'status': 'completed', 'conclusion': 'failure'}):
            with self.assertRaises(ValueError):
                publication_identity({**run, **changes}, REQUEST)
    def test_lost_response_reads_existing_operation(self):
        receipt = {**REQUEST, 'status': 'completed'}
        transport = Fixture([(0, {}), (200, {**REQUEST, 'status': 'migrated'}), (200, receipt)])
        self.assertEqual(release(REQUEST, transport, sleep=lambda _: None), receipt)
        self.assertEqual([call[0] for call in transport.calls], ['POST', 'GET', 'GET'])

    def test_missing_operation_retries_identical_contents(self):
        transport = Fixture([(0, {}), (404, {}), (200, {**REQUEST, 'status': 'completed'})])
        release(REQUEST, transport, sleep=lambda _: None)
        self.assertEqual(transport.calls[0][2], transport.calls[2][2])

    def test_failed_and_mismatched_receipts_cannot_be_success(self):
        receipt = {**REQUEST, 'status': 'needs_recovery'}
        self.assertEqual(release(REQUEST, Fixture([(409, receipt)]))['status'], 'needs_recovery')
        with self.assertRaises(ValueError):
            release(REQUEST, Fixture([(200, {**receipt, 'status': 'completed', 'source_sha': 'c' * 40})]))

    def test_pending_receipt_has_a_bounded_deadline(self):
        ticks = iter([0, 1, 601])
        with self.assertRaises(ValueError):
            release(REQUEST, Fixture([(0, {})]), sleep=lambda _: None, clock=lambda: next(ticks))

    def test_only_private_https_origin_is_selected(self):
        self.assertEqual(endpoint('https://example.ts.net/'), 'https://example.ts.net')
        for value in ('http://example.ts.net', 'https://example.com', 'https://example.ts.net:22',
                      'https://user:pass@example.ts.net', 'https://example.ts.net/?secret=value'):
            with self.assertRaises(ValueError):
                endpoint(value)
