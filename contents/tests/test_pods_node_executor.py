"""
Unit tests for pods-node-executor.py.

pods-node-executor.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common, so patches target pods_node_executor.common.
"""

import importlib
import os
import sys
import unittest

from unittest.mock import MagicMock, patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pods_node_executor = importlib.import_module('pods-node-executor')


class TestPodsNodeExecutor(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    @patch.object(pods_node_executor.common, 'run_interactive_command')
    @patch.object(pods_node_executor.common, 'verify_pod_exists')
    @patch.object(pods_node_executor.common, 'log_pod_parameters')
    @patch.object(pods_node_executor.common, 'get_core_node_parameter_list')
    @patch.object(pods_node_executor.common, 'connect')
    def test_main_runs_command_in_configured_container(
            self, mock_connect, mock_params, mock_log, mock_verify, mock_run):
        os.environ['RD_CONFIG_SHELL'] = '/bin/bash'
        os.environ['RD_CONFIG_COMMAND'] = 'echo hello'
        mock_params.return_value = ['my-pod', 'default', 'app']
        mock_run.return_value = (MagicMock(), False)

        pods_node_executor.main()

        name, namespace, container, exec_command = mock_run.call_args[0]
        self.assertEqual('my-pod', name)
        self.assertEqual('app', container)
        self.assertEqual(['/bin/bash', '-c', 'echo hello'], exec_command)

    @patch.object(pods_node_executor.common, 'run_interactive_command')
    @patch.object(pods_node_executor.common, 'verify_pod_exists')
    @patch.object(pods_node_executor.common, 'log_pod_parameters')
    @patch.object(pods_node_executor.common, 'get_core_node_parameter_list')
    @patch.object(pods_node_executor.common, 'connect')
    def test_main_prefers_exec_command_over_config_command(
            self, mock_connect, mock_params, mock_log, mock_verify, mock_run):
        os.environ['RD_CONFIG_SHELL'] = '/bin/bash'
        os.environ['RD_CONFIG_COMMAND'] = 'from-config'
        os.environ['RD_EXEC_COMMAND'] = 'from-exec'
        mock_params.return_value = ['my-pod', 'default', 'app']
        mock_run.return_value = (MagicMock(), False)

        pods_node_executor.main()

        self.assertEqual(['/bin/bash', '-c', 'from-exec'], mock_run.call_args[0][3])

    @patch.object(pods_node_executor.client, 'CoreV1Api')
    @patch.object(pods_node_executor.common, 'run_interactive_command')
    @patch.object(pods_node_executor.common, 'verify_pod_exists')
    @patch.object(pods_node_executor.common, 'log_pod_parameters')
    @patch.object(pods_node_executor.common, 'get_core_node_parameter_list')
    @patch.object(pods_node_executor.common, 'connect')
    def test_main_resolves_first_container_when_none_configured(
            self, mock_connect, mock_params, mock_log, mock_verify, mock_run, mock_api_class):
        os.environ['RD_CONFIG_SHELL'] = '/bin/bash'
        os.environ['RD_CONFIG_COMMAND'] = 'echo hello'
        mock_params.return_value = ['my-pod', 'default', None]
        status = MagicMock()
        status.spec.containers = [MagicMock(name='first')]
        status.spec.containers[0].name = 'sidecar'
        mock_api_class.return_value.read_namespaced_pod_status.return_value = status
        mock_run.return_value = (MagicMock(), False)

        pods_node_executor.main()

        self.assertEqual('sidecar', mock_run.call_args[0][2])
        # kubernetes 37 validates arguments and rejects pretty=True: pretty is a string.
        pretty = mock_api_class.return_value.read_namespaced_pod_status.call_args.kwargs['pretty']
        self.assertIsInstance(pretty, str)

    @patch.object(pods_node_executor.common, 'verify_pod_exists')
    @patch.object(pods_node_executor.common, 'log_pod_parameters')
    @patch.object(pods_node_executor.common, 'get_core_node_parameter_list')
    @patch.object(pods_node_executor.common, 'connect')
    def test_main_exits_when_no_command_is_given(
            self, mock_connect, mock_params, mock_log, mock_verify):
        # Upstream indexed os.environ directly, so a missing command raised
        # KeyError instead of telling the operator what was wrong.
        os.environ['RD_CONFIG_SHELL'] = '/bin/bash'
        mock_params.return_value = ['my-pod', 'default', 'app']

        with self.assertRaises(SystemExit) as cm:
            pods_node_executor.main()
        self.assertEqual(1, cm.exception.code)

    @patch.object(pods_node_executor.common, 'verify_pod_exists')
    @patch.object(pods_node_executor.common, 'get_core_node_parameter_list')
    @patch.object(pods_node_executor.common, 'connect')
    def test_main_exits_when_pod_name_is_missing(
            self, mock_connect, mock_params, mock_verify):
        os.environ['RD_CONFIG_COMMAND'] = 'echo hello'
        mock_params.return_value = [None, 'default', 'app']

        with self.assertRaises(SystemExit) as cm:
            pods_node_executor.main()
        self.assertEqual(1, cm.exception.code)

    @patch.object(pods_node_executor.common, 'run_interactive_command')
    @patch.object(pods_node_executor.common, 'verify_pod_exists')
    @patch.object(pods_node_executor.common, 'log_pod_parameters')
    @patch.object(pods_node_executor.common, 'get_core_node_parameter_list')
    @patch.object(pods_node_executor.common, 'connect')
    def test_main_exits_when_command_reports_error(
            self, mock_connect, mock_params, mock_log, mock_verify, mock_run):
        os.environ['RD_CONFIG_SHELL'] = '/bin/bash'
        os.environ['RD_CONFIG_COMMAND'] = 'false'
        mock_params.return_value = ['my-pod', 'default', 'app']
        mock_run.return_value = (MagicMock(), True)

        with self.assertRaises(SystemExit) as cm:
            pods_node_executor.main()
        self.assertEqual(1, cm.exception.code)


if __name__ == '__main__':
    unittest.main()
