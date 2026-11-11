"""
Unit tests for pods-copy-file.py.

pods-copy-file.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common, so patches target pods_copy_file.common.
"""

import importlib
import io
import os
import sys
import unittest

from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pods_copy_file = importlib.import_module('pods-copy-file')


class TestPodsCopyFile(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    @patch.object(pods_copy_file.common, 'copy_file')
    @patch.object(pods_copy_file.common, 'log_pod_parameters')
    @patch.object(pods_copy_file.common, 'verify_pod_exists')
    @patch.object(pods_copy_file.common, 'get_core_node_parameter_list')
    @patch.object(pods_copy_file.common, 'connect')
    def test_main_copies_file_to_pod(self, mock_connect, mock_params, mock_verify,
                                     mock_log, mock_copy):
        os.environ['RD_FILE_COPY_FILE'] = '/local/script.sh'
        os.environ['RD_FILE_COPY_DESTINATION'] = '/tmp/script.sh'
        mock_params.return_value = ['my-pod', 'default', 'app']

        out = io.StringIO()
        with redirect_stdout(out):
            pods_copy_file.main()

        mock_copy.assert_called_once_with(
            'my-pod', 'default', 'app', '/local/script.sh', '/tmp', 'script.sh')
        self.assertIn('/tmp/script.sh', out.getvalue())

    @patch.object(pods_copy_file.client, 'CoreV1Api')
    @patch.object(pods_copy_file.common, 'copy_file')
    @patch.object(pods_copy_file.common, 'log_pod_parameters')
    @patch.object(pods_copy_file.common, 'get_core_node_parameter_list')
    @patch.object(pods_copy_file.common, 'connect')
    def test_main_copies_to_first_container_when_none_configured(
            self, mock_connect, mock_params, mock_log, mock_copy, mock_api_class):
        os.environ['RD_FILE_COPY_FILE'] = '/local/script.sh'
        os.environ['RD_FILE_COPY_DESTINATION'] = '/tmp/script.sh'
        mock_params.return_value = ['my-pod', 'default', None]
        status = MagicMock()
        status.spec.containers = [MagicMock()]
        status.spec.containers[0].name = 'sidecar'
        mock_api_class.return_value.read_namespaced_pod_status.return_value = status

        with redirect_stdout(io.StringIO()):
            pods_copy_file.main()

        mock_copy.assert_called_once_with(
            'my-pod', 'default', 'sidecar', '/local/script.sh', '/tmp', 'script.sh')
        # kubernetes 37 validates arguments and rejects pretty=True: pretty is a string.
        pretty = mock_api_class.return_value.read_namespaced_pod_status.call_args.kwargs['pretty']
        self.assertIsInstance(pretty, str)

    @patch.object(pods_copy_file.common, 'get_core_node_parameter_list')
    @patch.object(pods_copy_file.common, 'connect')
    def test_main_exits_when_pod_name_is_missing(self, mock_connect, mock_params):
        os.environ['RD_FILE_COPY_FILE'] = '/local/script.sh'
        os.environ['RD_FILE_COPY_DESTINATION'] = '/tmp/script.sh'
        mock_params.return_value = [None, 'default', 'app']

        with self.assertRaises(SystemExit) as cm:
            pods_copy_file.main()
        self.assertEqual(1, cm.exception.code)

    @patch.object(pods_copy_file.common, 'verify_pod_exists')
    @patch.object(pods_copy_file.common, 'get_core_node_parameter_list')
    @patch.object(pods_copy_file.common, 'connect')
    def test_main_exits_when_source_file_is_missing(self, mock_connect, mock_params,
                                                    mock_verify):
        os.environ['RD_FILE_COPY_DESTINATION'] = '/tmp/script.sh'
        mock_params.return_value = ['my-pod', 'default', 'app']

        with self.assertRaises(SystemExit) as cm:
            pods_copy_file.main()
        self.assertEqual(1, cm.exception.code)

    @patch.object(pods_copy_file.common, 'copy_file')
    @patch.object(pods_copy_file.common, 'log_pod_parameters')
    @patch.object(pods_copy_file.common, 'verify_pod_exists')
    @patch.object(pods_copy_file.common, 'get_core_node_parameter_list')
    @patch.object(pods_copy_file.common, 'connect')
    def test_main_exits_when_copy_fails(self, mock_connect, mock_params, mock_verify,
                                        mock_log, mock_copy):
        os.environ['RD_FILE_COPY_FILE'] = '/local/script.sh'
        os.environ['RD_FILE_COPY_DESTINATION'] = '/tmp/script.sh'
        mock_params.return_value = ['my-pod', 'default', 'app']
        mock_copy.side_effect = RuntimeError('stream closed')

        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            pods_copy_file.main()
        self.assertEqual(1, cm.exception.code)


if __name__ == '__main__':
    unittest.main()
