"""
Unit tests for pods-wait.py.

pods-wait.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common, so patches target pods_wait.common.
"""

import importlib
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pods_wait = importlib.import_module('pods-wait')


def pod(*ready):
    """A pod with one container status for each value of ready."""
    statuses = [SimpleNamespace(name='c%d' % i, ready=r) for i, r in enumerate(ready)]
    return SimpleNamespace(status=SimpleNamespace(container_statuses=statuses or None))


class TestWait(unittest.TestCase):

    def setUp(self):
        os.environ.clear()
        os.environ.update({
            'RD_CONFIG_NAME': 'my-pod',
            'RD_CONFIG_NAMESPACE': 'default',
            'RD_CONFIG_RETRIES': '2',
            'RD_CONFIG_SLEEP': '1',
        })

    def run_wait(self, pods):
        """Run wait(), which reads the next entry of pods each time. Returns
        the exit code."""
        with patch.object(pods_wait.time, 'sleep'), \
                patch.object(pods_wait.client, 'CoreV1Api') as api, \
                redirect_stdout(io.StringIO()), \
                self.assertRaises(SystemExit) as exited:
            read = api.return_value.read_namespaced_pod_status
            read.side_effect = pods
            pods_wait.wait()

        self.reads = read.call_count
        return exited.exception.code

    def test_a_pod_with_every_container_ready_is_ready(self):
        self.assertEqual(0, self.run_wait([pod(True, True)]))
        self.assertEqual(1, self.reads)

    def test_waits_for_the_other_containers_when_the_first_is_ready(self):
        self.assertEqual(0, self.run_wait([pod(True, False), pod(True, True)]))
        self.assertEqual(2, self.reads)

    def test_fails_when_a_container_never_becomes_ready(self):
        with self.assertLogs('kubernetes-wait-pod', level='ERROR'):
            self.assertEqual(1, self.run_wait([pod(True, False)] * 3))

    def test_waits_for_a_pod_that_has_no_container_statuses_yet(self):
        self.assertEqual(0, self.run_wait([pod(), pod(True)]))


if __name__ == '__main__':
    unittest.main()
