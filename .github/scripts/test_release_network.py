import json
import unittest
from release_network import denied, targets


class DenialTests(unittest.TestCase):
    def test_only_actual_timeout_proves_denial(self):
        entry = {'host': '100.64.1.2', 'port': 443}
        def blocked(*_args, **_kwargs):
            raise TimeoutError()
        self.assertTrue(denied(entry, blocked))
        def closed(*_args, **_kwargs):
            raise ConnectionRefusedError()
        with self.assertRaises(ValueError):
            denied(entry, closed)
        class Reachable:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                pass
        with self.assertRaises(ValueError):
            denied(entry, lambda *_args, **_kwargs: Reachable())

    def test_incomplete_or_public_target_selection_fails(self):
        private = [{'host': '100.64.1.2', 'port': 20 + i} for i in range(7)]
        self.assertEqual(targets(json.dumps(private)), private)
        for value in (private[:1], [*private[:-1], {'host': '1.1.1.1', 'port': 443}],
                      [*private[:-1], {'host': '100.64.1.2', 'port': 443, 'command': 'arbitrary'}]):
            with self.assertRaises(ValueError):
                targets(json.dumps(value))
