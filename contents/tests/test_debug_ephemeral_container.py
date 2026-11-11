"""
Unit tests for debug-ephemeral-container.py.

debug-ephemeral-container.py has a hyphenated filename, so it is loaded with
importlib. It does "import common", which resolves through the inserted
sys.path to a module object distinct from contents.common, so patches target
debug_ephemeral_container.common.
"""

import importlib
import io
import os
import sys
import unittest

from contextlib import redirect_stdout
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

debug_ephemeral_container = importlib.import_module('debug-ephemeral-container')


@patch.object(debug_ephemeral_container.common, 'verify_pod_exists')
@patch.object(debug_ephemeral_container.common, 'connect')
@patch.object(debug_ephemeral_container.client, 'CoreV1Api')
class TestDebugEphemeralContainer(unittest.TestCase):

    def setUp(self):
        os.environ.clear()
        os.environ['RD_CONFIG_NAME'] = 'my-pod'
        os.environ['RD_CONFIG_NAMESPACE'] = 'prod'
        os.environ['RD_CONFIG_CONTAINER_NAME'] = 'debugger'
        os.environ['RD_CONFIG_CONTAINER_IMAGE'] = 'busybox'

    def run_step(self, mock_api_class):
        out = io.StringIO()
        with redirect_stdout(out):
            debug_ephemeral_container.main()
        patch_call = mock_api_class.return_value.patch_namespaced_pod_ephemeralcontainers
        patch_call.assert_called_once()
        name, namespace, body = patch_call.call_args.args
        self.assertEqual(('my-pod', 'prod'), (name, namespace))
        return body['spec']['ephemeralContainers'], out.getvalue()

    def test_main_adds_container_without_target_when_none_is_set(
            self, mock_api_class, mock_connect, mock_verify):
        # Target Container is optional. Without it the ephemeral container
        # uses the pod's namespaces, so targetContainerName is left out.
        containers, out = self.run_step(mock_api_class)

        self.assertEqual(
            [{'name': 'debugger', 'image': 'busybox', 'stdin': True, 'tty': True}],
            containers)
        self.assertIn('Ephemeral container debugger successfully added to pod my-pod', out)

    def test_main_targets_the_configured_container(
            self, mock_api_class, mock_connect, mock_verify):
        os.environ['RD_CONFIG_TARGET_CONTAINER'] = 'app'

        containers, _ = self.run_step(mock_api_class)

        self.assertEqual(
            [{'name': 'debugger', 'image': 'busybox', 'targetContainerName': 'app',
              'stdin': True, 'tty': True}],
            containers)


if __name__ == '__main__':
    unittest.main()
