"""Credential boundary failures must stop commissioning without a release request."""
import unittest
from release_access import verify


class AccessTests(unittest.TestCase):
    def fixture(self, override=None):
        calls = []
        def call(token, method, app):
            calls.append((token, method, app))
            if override and override[0] == (token, method, app): return override[1]
            if token == 'read' and method == 'GET' and app == 'securo-production':
                return 200, {'operations': []}
            if token == 'deploy' and method == 'POST' and app == 'securo-production':
                return 400, {'error': 'Unknown mutation'}
            return 401, {'error': 'Unauthorized'}
        return calls, call

    def test_scopes_verify_without_a_release_body(self):
        calls, call = self.fixture()
        self.assertTrue(verify(call)['no_operation_admitted'])
        self.assertEqual(len(calls), 8)

    def test_read_mutation_other_app_and_deploy_read_access_fail(self):
        for entry in (('read', 'POST', 'securo-production'),
                      ('read', 'GET', 'securo-ci-test'),
                      ('deploy', 'GET', 'securo-production')):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                verify(self.fixture((entry, (200, {})))[1])

    def test_invalid_deploy_token_cannot_pass_as_valid_authentication(self):
        with self.assertRaises(ValueError):
            verify(self.fixture((('deploy', 'POST', 'securo-production'),
                                (401, {'error': 'Unauthorized'})))[1])

    def test_changed_release_history_requires_reconciliation(self):
        _, base = self.fixture()
        reads = []
        def call(token, method, app):
            result = base(token, method, app)
            if (token, method, app) == ('read', 'GET', 'securo-production'):
                reads.append(1)
                if len(reads) == 2: return 200, {'operations': [{'status': 'running'}]}
            return result
        with self.assertRaises(ValueError): verify(call)


if __name__ == '__main__': unittest.main()
