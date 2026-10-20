"""
Unit tests for pods-run-script.py.

pods-run-script.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common, so patches target pods_run_script.common.
"""

import importlib
import io
import os
import sys
import unittest

from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from kubernetes.client.rest import ApiException


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pods_run_script = importlib.import_module('pods-run-script')


class TestPodsRunScript(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    def _run_main(self, mock_run_command, mock_interactive, stdout=b'ok', stderr=b''):
        resp = MagicMock()
        resp.peek_stdout.return_value = bool(stdout)
        resp.read_stdout.return_value = stdout
        resp.peek_stderr.return_value = bool(stderr)
        resp.read_stderr.return_value = stderr
        mock_run_command.return_value = resp
        mock_interactive.return_value = (resp, False)
        out = io.StringIO()
        with redirect_stdout(out):
            pods_run_script.main()
        return out.getvalue()

    @patch.object(pods_run_script.common, 'run_interactive_command')
    @patch.object(pods_run_script.common, 'run_command')
    @patch.object(pods_run_script.common, 'copy_file')
    @patch.object(pods_run_script.common, 'log_pod_parameters')
    @patch.object(pods_run_script.client, 'CoreV1Api')
    @patch.object(pods_run_script.common, 'verify_pod_exists')
    @patch.object(pods_run_script.common, 'get_core_node_parameter_list')
    @patch.object(pods_run_script.common, 'connect')
    def test_main_copies_script_and_makes_it_executable(
            self, mock_connect, mock_params, mock_verify, mock_api_class,
            mock_log, mock_copy, mock_run_command, mock_interactive):
        os.environ['RD_CONFIG_SCRIPT'] = 'echo hello'
        mock_params.return_value = ['my-pod', 'default', 'app']
        mock_api_class.return_value.read_namespaced_pod.return_value = MagicMock()

        output = self._run_main(mock_run_command, mock_interactive)

        mock_copy.assert_called_once()
        self.assertEqual('my-pod', mock_copy.call_args[1]['name'])
        chmod = mock_run_command.call_args_list[0][1]['command']
        self.assertEqual(['chmod', '+x'], chmod[:2])
        self.assertIn('ok', output)

    @patch.object(pods_run_script.common, 'delete_pod')
    @patch.object(pods_run_script.common, 'run_interactive_command')
    @patch.object(pods_run_script.common, 'run_command')
    @patch.object(pods_run_script.common, 'copy_file')
    @patch.object(pods_run_script.common, 'log_pod_parameters')
    @patch.object(pods_run_script.client, 'CoreV1Api')
    @patch.object(pods_run_script.common, 'verify_pod_exists')
    @patch.object(pods_run_script.common, 'get_core_node_parameter_list')
    @patch.object(pods_run_script.common, 'connect')
    def test_main_reports_but_survives_a_failed_cleanup(
            self, mock_connect, mock_params, mock_verify, mock_api_class,
            mock_log, mock_copy, mock_run_command, mock_interactive, mock_delete):
        # Cleanup only runs because the script already failed. A failure to
        # delete must not replace that with a traceback from the cleanup.
        os.environ['RD_CONFIG_SCRIPT'] = 'echo hello'
        os.environ['RD_CONFIG_DELETEONFAIL'] = 'true'
        mock_params.return_value = ['my-pod', 'default', 'app']
        resp = MagicMock()
        resp.peek_stdout.return_value = False
        resp.peek_stderr.return_value = False
        mock_run_command.return_value = resp
        mock_interactive.return_value = (resp, True)
        mock_delete.side_effect = ApiException(status=500, reason='boom')

        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            pods_run_script.main()

        self.assertEqual(1, cm.exception.code)
        mock_delete.assert_called_once()

    @patch.object(pods_run_script.common, 'verify_pod_exists')
    @patch.object(pods_run_script.common, 'get_core_node_parameter_list')
    @patch.object(pods_run_script.common, 'connect')
    def test_main_exits_when_no_script_is_given(
            self, mock_connect, mock_params, mock_verify):
        # Upstream called .encode on the result of os.environ.get, so a missing
        # script raised AttributeError on None rather than saying what was wrong.
        mock_params.return_value = ['my-pod', 'default', 'app']

        with self.assertRaises(SystemExit) as cm:
            pods_run_script.main()
        self.assertEqual(1, cm.exception.code)

    @patch.object(pods_run_script.common, 'verify_pod_exists')
    @patch.object(pods_run_script.common, 'get_core_node_parameter_list')
    @patch.object(pods_run_script.common, 'connect')
    def test_main_exits_when_pod_name_is_missing(
            self, mock_connect, mock_params, mock_verify):
        os.environ['RD_CONFIG_SCRIPT'] = 'echo hello'
        mock_params.return_value = [None, 'default', 'app']

        with self.assertRaises(SystemExit) as cm:
            pods_run_script.main()
        self.assertEqual(1, cm.exception.code)

    @patch.object(pods_run_script.client, 'CoreV1Api')
    @patch.object(pods_run_script.common, 'verify_pod_exists')
    @patch.object(pods_run_script.common, 'get_core_node_parameter_list')
    @patch.object(pods_run_script.common, 'connect')
    def test_main_exits_when_pod_is_missing(
            self, mock_connect, mock_params, mock_verify, mock_api_class):
        os.environ['RD_CONFIG_SCRIPT'] = 'echo hello'
        mock_params.return_value = ['my-pod', 'default', 'app']
        mock_verify.side_effect = SystemExit(1)

        with self.assertRaises(SystemExit) as cm:
            pods_run_script.main()
        self.assertEqual(1, cm.exception.code)

    @patch.object(pods_run_script.common, 'run_interactive_command')
    @patch.object(pods_run_script.common, 'run_command')
    @patch.object(pods_run_script.common, 'copy_file')
    @patch.object(pods_run_script.common, 'log_pod_parameters')
    @patch.object(pods_run_script.client, 'CoreV1Api')
    @patch.object(pods_run_script.common, 'verify_pod_exists')
    @patch.object(pods_run_script.common, 'get_core_node_parameter_list')
    @patch.object(pods_run_script.common, 'connect')
    def test_main_resolves_first_container_when_none_configured(
            self, mock_connect, mock_params, mock_verify, mock_client_api,
            mock_log, mock_copy, mock_run_command, mock_interactive):
        os.environ['RD_CONFIG_SCRIPT'] = 'echo hello'
        mock_params.return_value = ['my-pod', 'default', None]
        status = MagicMock()
        status.spec.containers = [MagicMock()]
        status.spec.containers[0].name = 'sidecar'
        mock_client_api.return_value.read_namespaced_pod_status.return_value = status

        self._run_main(mock_run_command, mock_interactive)

        self.assertEqual('sidecar', mock_copy.call_args[1]['container'])


class TestPodsRunScriptRemovesScript(unittest.TestCase):
    """The copied script can hold secrets expanded from job options, so it
    must not be left in the container when a step fails."""

    def setUp(self):
        os.environ.clear()
        os.environ['RD_CONFIG_SCRIPT'] = 'echo hello'

    @staticmethod
    def _resp(stderr=b''):
        resp = MagicMock()
        resp.peek_stdout.return_value = False
        resp.peek_stderr.return_value = bool(stderr)
        resp.read_stderr.return_value = stderr
        return resp

    def _run(self, chmod_stderr=b'', script_fails=False, rm_fails=False,
             delete_on_fail=False):
        """Run main() and return (exit code, chmod command, rm commands,
        delete_pod mock). rm_fails is True for an rm that exits with an
        error, or an exception the rm call raises."""
        if delete_on_fail:
            os.environ['RD_CONFIG_DELETEONFAIL'] = 'true'

        rm_commands = []

        def run_interactive_command(command, **_):
            if command[0] != 'rm':
                return self._resp(), script_fails
            rm_commands.append(command)
            if isinstance(rm_fails, BaseException):
                raise rm_fails
            return self._resp(), rm_fails

        with patch.object(pods_run_script.common, 'connect'), \
                patch.object(pods_run_script.common, 'get_core_node_parameter_list',
                             return_value=['my-pod', 'default', 'app']), \
                patch.object(pods_run_script.common, 'verify_pod_exists'), \
                patch.object(pods_run_script.client, 'CoreV1Api'), \
                patch.object(pods_run_script.common, 'log_pod_parameters'), \
                patch.object(pods_run_script.common, 'copy_file'), \
                patch.object(pods_run_script.common, 'run_command',
                             return_value=self._resp(chmod_stderr)) as run_command, \
                patch.object(pods_run_script.common, 'run_interactive_command',
                             side_effect=run_interactive_command), \
                patch.object(pods_run_script.common, 'delete_pod') as delete_pod, \
                redirect_stdout(io.StringIO()):
            code = 0
            try:
                pods_run_script.main()
            except SystemExit as e:
                code = e.code
        chmod = run_command.call_args.kwargs['command']
        return code, chmod, rm_commands, delete_pod

    def test_removes_the_script_after_a_successful_run(self):
        code, chmod, rm_commands, _ = self._run()

        self.assertEqual(0, code)
        self.assertEqual([['rm', chmod[2]]], rm_commands)

    def test_removes_the_script_when_the_script_fails(self):
        code, chmod, rm_commands, _ = self._run(script_fails=True)

        self.assertEqual(1, code)
        self.assertEqual([['rm', chmod[2]]], rm_commands)

    def test_removes_the_script_when_it_cannot_be_made_executable(self):
        code, chmod, rm_commands, _ = self._run(chmod_stderr=b'chmod: denied')

        self.assertEqual(1, code)
        self.assertEqual([['rm', chmod[2]]], rm_commands)

    def test_does_not_try_to_remove_the_script_from_a_deleted_pod(self):
        code, _, rm_commands, delete_pod = self._run(script_fails=True, delete_on_fail=True)

        self.assertEqual(1, code)
        delete_pod.assert_called_once()
        self.assertEqual([], rm_commands)

    def test_keeps_the_script_failure_when_removing_the_script_also_fails(self):
        code, _, rm_commands, _ = self._run(
            script_fails=True, rm_fails=ApiException(status=500, reason='boom'))

        self.assertEqual(1, code)
        self.assertEqual(1, len(rm_commands))

    def test_still_fails_when_the_script_cannot_be_removed_after_success(self):
        # rm runs without a TTY, so its failure is reported by the exec exit
        # status rather than by output on stderr.
        code, _, rm_commands, _ = self._run(rm_fails=True)

        self.assertEqual(1, code)
        self.assertEqual(1, len(rm_commands))


if __name__ == '__main__':
    unittest.main()
