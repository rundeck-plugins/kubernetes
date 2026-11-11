"""
Unit tests for pods-create.py.

pods-create.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common, so patches target pods_create.common.
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

pods_create = importlib.import_module('pods-create')


def create_data(**overrides):
    data = {
        'name': 'my-pod',
        'namespace': 'default',
        'container_name': 'app',
        'api_version': 'v1',
        'image': 'nginx:latest',
        'labels': 'app=web,env=prod',
        'ports': None,
    }
    data.update(overrides)
    return data


class TestCreatePod(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    def test_create_pod_keeps_equals_signs_in_label_values(self):
        # Splitting on every '=' raised "too many values to unpack" instead of
        # saying what was wrong with the input.
        pod = pods_create.create_pod(create_data(labels='token=a=b'))
        self.assertEqual({'token': 'a=b'}, pod.metadata.labels)

    def test_create_pod_reports_labels_that_are_not_pairs(self):
        with self.assertRaises(SystemExit) as cm:
            pods_create.create_pod(create_data(labels='notapair'))
        self.assertEqual(1, cm.exception.code)

    def test_create_pod_tolerates_empty_labels(self):
        # labels is required in plugin.yaml, but an empty value satisfies that
        # check and used to reach ''.split('=') as a bare ValueError.
        pod = pods_create.create_pod(create_data(labels=''))
        self.assertEqual({}, pod.metadata.labels)

    def test_create_pod_builds_metadata_from_labels(self):
        pod = pods_create.create_pod(create_data())

        self.assertEqual('Pod', pod.kind)
        self.assertEqual('v1', pod.api_version)
        self.assertEqual('my-pod', pod.metadata.name)
        self.assertEqual('default', pod.metadata.namespace)
        self.assertEqual({'app': 'web', 'env': 'prod'}, pod.metadata.labels)


class TestPodsCreateMain(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    def _configure(self):
        os.environ['RD_CONFIG_NAME'] = 'my-pod'
        os.environ['RD_CONFIG_NAMESPACE'] = 'default'
        os.environ['RD_CONFIG_CONTAINER_NAME'] = 'app'
        os.environ['RD_CONFIG_API_VERSION'] = 'v1'
        os.environ['RD_CONFIG_IMAGE'] = 'nginx:latest'
        os.environ['RD_CONFIG_LABELS'] = 'app=web'

    @patch.object(pods_create.core_v1_api, 'CoreV1Api')
    @patch.object(pods_create.common, 'log_pod_parameters')
    @patch.object(pods_create.common, 'connect')
    def test_main_creates_the_pod(self, mock_connect, mock_log, mock_api_class):
        self._configure()
        mock_api_class.return_value.create_namespaced_pod.return_value = MagicMock()

        out = io.StringIO()
        with redirect_stdout(out):
            pods_create.main()

        kwargs = mock_api_class.return_value.create_namespaced_pod.call_args[1]
        self.assertEqual('default', kwargs['namespace'])
        self.assertEqual('my-pod', kwargs['body'].metadata.name)
        self.assertIn('Pod Created successfully', out.getvalue())

    @patch.object(pods_create.core_v1_api, 'CoreV1Api')
    @patch.object(pods_create.common, 'log_pod_parameters')
    @patch.object(pods_create.common, 'connect')
    def test_main_exits_on_api_exception(self, mock_connect, mock_log, mock_api_class):
        self._configure()
        mock_api_class.return_value.create_namespaced_pod.side_effect = ApiException(
            status=409, reason='AlreadyExists')

        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            pods_create.main()
        self.assertEqual(1, cm.exception.code)

    @patch.object(pods_create.core_v1_api, 'CoreV1Api')
    @patch.object(pods_create.common, 'log_pod_parameters')
    @patch.object(pods_create.common, 'connect')
    def test_main_logs_a_wrongly_typed_option_and_exits(
            self, mock_connect, mock_log, mock_api_class):
        # Kubernetes client 37 rejects the string while building the probe and
        # raises a pydantic ValidationError (a ValueError). Older clients send
        # it, and the API server rejects it, as the mocked call does here.
        self._configure()
        os.environ['RD_CONFIG_LIVENESS_PROBE'] = 'initialDelaySeconds: "5"'
        mock_api_class.return_value.create_namespaced_pod.side_effect = ApiException(
            status=400, reason='Bad Request')

        with redirect_stdout(io.StringIO()), \
                self.assertLogs('kubernetes-create-pod', level='ERROR') as logs, \
                self.assertRaises(SystemExit) as cm:
            pods_create.main()

        self.assertEqual(1, cm.exception.code)
        self.assertIn('Exception creating pod my-pod', logs.output[0])

    @patch.object(pods_create.core_v1_api, 'CoreV1Api')
    @patch.object(pods_create.common, 'log_pod_parameters')
    @patch.object(pods_create.common, 'connect')
    def test_main_does_not_report_success_when_nothing_was_created(
            self, mock_connect, mock_log, mock_api_class):
        self._configure()
        mock_api_class.return_value.create_namespaced_pod.return_value = None

        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            pods_create.main()

        self.assertEqual(1, cm.exception.code)
        self.assertNotIn('Pod Created successfully', out.getvalue())

    @patch.object(pods_create.core_v1_api, 'CoreV1Api')
    @patch.object(pods_create.common, 'log_pod_parameters')
    @patch.object(pods_create.common, 'connect')
    def test_main_passes_optional_settings_through(
            self, mock_connect, mock_log, mock_api_class):
        self._configure()
        os.environ['RD_CONFIG_PORTS'] = '8080'
        os.environ['RD_CONFIG_ENVIRONMENTS'] = 'KEY=value'
        mock_api_class.return_value.create_namespaced_pod.return_value = MagicMock()

        with redirect_stdout(io.StringIO()):
            pods_create.main()

        container = mock_api_class.return_value.create_namespaced_pod.call_args[1][
            'body'].spec.containers[0]
        self.assertEqual('nginx:latest', container.image)
        self.assertEqual('app', container.name)


if __name__ == '__main__':
    unittest.main()
