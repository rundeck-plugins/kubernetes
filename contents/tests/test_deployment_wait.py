"""
Unit tests for deployment-wait.py.

deployment-wait.py has a hyphenated filename, so it is loaded with importlib.
It does "import common", which resolves through the inserted sys.path to a
module object distinct from contents.common, so patches target
deployment_wait.common.
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

deployment_wait = importlib.import_module('deployment-wait')


def deployment(wanted=3, generation=1, observed_generation=1, replicas=None,
               updated=None, ready=None, available=None, unavailable=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(generation=generation),
        spec=SimpleNamespace(replicas=wanted),
        status=SimpleNamespace(observed_generation=observed_generation,
                               replicas=replicas,
                               updated_replicas=updated,
                               ready_replicas=ready,
                               available_replicas=available,
                               unavailable_replicas=unavailable))


ROLLED_OUT = deployment(replicas=3, updated=3, ready=3, available=3)


class TestWait(unittest.TestCase):

    def setUp(self):
        os.environ.clear()
        os.environ.update({
            'RD_CONFIG_NAME': 'web',
            'RD_CONFIG_NAMESPACE': 'default',
            'RD_CONFIG_RETRIES': '3',
            'RD_CONFIG_SLEEP': '1',
        })

    def run_wait(self, deployments):
        """Run wait(), which reads the next entry of deployments each time.
        Returns the exit code, or None if wait() returned normally."""
        with patch.object(deployment_wait.time, 'sleep'), \
                patch.object(deployment_wait.client, 'AppsV1Api') as api, \
                redirect_stdout(io.StringIO()), \
                self.assertLogs('kubernetes-model-source', level='INFO') as logs:
            read = api.return_value.read_namespaced_deployment
            read.side_effect = deployments
            try:
                deployment_wait.wait()
                exit_code = None
            except SystemExit as e:
                exit_code = e.code

        self.reads = read.call_count
        self.log_output = logs.output
        return exit_code

    def test_returns_at_once_when_the_rollout_is_complete(self):
        self.assertIsNone(self.run_wait([ROLLED_OUT]))

        self.assertEqual(1, self.reads)
        self.assertIn('INFO:kubernetes-model-source:Deployment is ready', self.log_output)

    def test_waits_for_a_deployment_that_was_just_created(self):
        # The controller has not filled in the status yet.
        just_created = deployment(observed_generation=None)

        self.assertIsNone(self.run_wait([just_created, ROLLED_OUT]))

        self.assertEqual(2, self.reads)

    def test_waits_until_the_controller_has_seen_an_update(self):
        # The old pods are all ready, and the status still describes them.
        not_observed = deployment(generation=2, observed_generation=1,
                                  replicas=3, updated=3, ready=3, available=3)
        rolled_out = deployment(generation=2, observed_generation=2,
                                replicas=3, updated=3, ready=3, available=3)

        self.assertIsNone(self.run_wait([not_observed, rolled_out]))

        self.assertEqual(2, self.reads)

    def test_waits_while_old_pods_are_still_being_replaced(self):
        # A surge pod is starting: nothing is unavailable, and three pods
        # are ready, but only one of them runs the new spec.
        surging = deployment(replicas=4, updated=1, ready=3, available=3)

        self.assertIsNone(self.run_wait([surging, ROLLED_OUT]))

        self.assertEqual(2, self.reads)

    def test_a_deployment_scaled_to_zero_is_ready(self):
        self.assertIsNone(self.run_wait([deployment(wanted=0)]))

    def test_fails_when_the_retries_run_out(self):
        stuck = deployment(replicas=3, updated=3, ready=1, available=1, unavailable=2)

        self.assertEqual(1, self.run_wait([stuck] * 4))

        self.assertEqual(4, self.reads)
        self.assertIn('ERROR:kubernetes-model-source:number of retries exceeded',
                      self.log_output)

    def test_fails_when_no_pods_could_be_created(self):
        # The controller has seen the Deployment but could create no pod,
        # for example because a quota forbids it, so every counter stays
        # unset. Comparing replicas with ready_replicas called that ready.
        no_pods = deployment()

        self.assertEqual(1, self.run_wait([no_pods] * 4))

        self.assertEqual(4, self.reads)
        self.assertNotIn('INFO:kubernetes-model-source:Deployment is ready', self.log_output)
        self.assertIn('ERROR:kubernetes-model-source:number of retries exceeded',
                      self.log_output)


if __name__ == '__main__':
    unittest.main()
