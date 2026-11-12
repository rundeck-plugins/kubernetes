"""
Unit tests for create-from-yaml.py.

create-from-yaml.py has a hyphenated filename, so it is loaded with importlib.
It does "import common", which resolves through the inserted sys.path to a
module object distinct from contents.common, so patches target
create_from_yaml.common. The dynamic client is patched where the script looks
it up, as kubernetes.dynamic.DynamicClient.
"""

import datetime
import importlib
import io
import ast
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import yaml
from kubernetes.client.rest import ApiException
from kubernetes.dynamic.exceptions import ConflictError, ResourceNotFoundError
from kubernetes.dynamic.resource import ResourceInstance


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

create_from_yaml = importlib.import_module('create-from-yaml')


# Each of these is valid for the API server, which stores the quantities as
# "1" and "500m", drops the misspelled field and keeps the annotation as the
# string "2026-01-01". kubernetes 37's typed models reject all three.
POD_YAML = """
apiVersion: v1
kind: Pod
metadata:
  name: web
  annotations:
    deployed: 2026-01-01
spec:
  containers:
  - name: app
    image: nginx
    imagePullPolicyy: Always
    resources:
      requests:
        cpu: 0.5
      limits:
        cpu: 1
        nvidia.com/gpu: 1
"""

STORAGE_CLASS_YAML = """
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast
provisioner: example.com/fast
"""


def created(instance):
    return ResourceInstance(None, instance)


def printed(text):
    """Parse the step output. Typed models print as JSON on kubernetes
    client 37 and as a Python dict repr on older clients."""
    try:
        return json.loads(text)
    except ValueError:
        return ast.literal_eval(text)


class TestCreateFromYamlMain(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    def _configure(self, type_, yaml_string, namespace='apps'):
        os.environ['RD_CONFIG_TYPE'] = type_
        os.environ['RD_CONFIG_YAML'] = yaml_string
        os.environ['RD_CONFIG_NAMESPACE'] = namespace

    def _resource(self, mock_dynamic, namespaced=True):
        resource = mock_dynamic.return_value.resources.get.return_value
        resource.namespaced = namespaced
        resource.create.return_value = created(
            {'kind': 'Pod', 'metadata': {'name': 'web'}, 'status': {'phase': 'Pending'}})
        return resource

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_sends_the_yaml_unchanged(self, mock_connect, mock_dynamic):
        # The typed create_namespaced_pod of kubernetes 37 raised a pydantic
        # ValidationError for this YAML before sending anything.
        self._configure('Pod', POD_YAML)
        resource = self._resource(mock_dynamic)

        with redirect_stdout(io.StringIO()):
            create_from_yaml.main()

        mock_dynamic.return_value.resources.get.assert_called_once_with(
            api_version='v1', kind='Pod')
        resource.create.assert_called_once_with(
            body=yaml.safe_load(POD_YAML), namespace='apps')
        body = resource.create.call_args[1]['body']
        self.assertEqual(1, body['spec']['containers'][0]['resources']['limits']['cpu'])
        self.assertEqual(datetime.date(2026, 1, 1),
                         body['metadata']['annotations']['deployed'])

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_creates_cluster_scoped_types_without_a_namespace(
            self, mock_connect, mock_dynamic):
        self._configure('StorageClass', STORAGE_CLASS_YAML)
        resource = self._resource(mock_dynamic, namespaced=False)

        with redirect_stdout(io.StringIO()):
            create_from_yaml.main()

        mock_dynamic.return_value.resources.get.assert_called_once_with(
            api_version='storage.k8s.io/v1', kind='StorageClass')
        self.assertIsNone(resource.create.call_args[1]['namespace'])

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_uses_the_api_version_of_the_typed_api_it_replaces(
            self, mock_connect, mock_dynamic):
        expected = {
            'Pod': 'v1', 'ConfigMap': 'v1', 'Service': 'v1', 'Secret': 'v1',
            'PersistentVolume': 'v1', 'PersistentVolumeClaim': 'v1',
            'Deployment': 'apps/v1', 'StatefulSet': 'apps/v1',
            'Job': 'batch/v1', 'Ingress': 'networking.k8s.io/v1',
            'StorageClass': 'storage.k8s.io/v1',
        }
        self._resource(mock_dynamic)
        for type_, api_version in expected.items():
            with self.subTest(type_):
                self._configure(type_, 'kind: %s\n' % type_)
                with redirect_stdout(io.StringIO()):
                    create_from_yaml.main()
                mock_dynamic.return_value.resources.get.assert_called_with(
                    api_version=api_version, kind=type_)

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_prints_the_status(self, mock_connect, mock_dynamic):
        self._configure('Pod', POD_YAML)
        self._resource(mock_dynamic)

        out = io.StringIO()
        with redirect_stdout(out):
            create_from_yaml.main()

        # Same snake_case output as the typed create_namespaced_pod printed
        status = printed(out.getvalue())
        self.assertEqual('Pending', status['phase'])
        self.assertIn('pod_ip', status)
        self.assertIsNone(status['pod_ip'])

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_prints_the_statefulset_status_in_snake_case(
            self, mock_connect, mock_dynamic):
        # rundeckpro's StatefulSetOperationsSpec looks for this line
        self._configure('StatefulSet', 'kind: StatefulSet\n')
        resource = self._resource(mock_dynamic)
        resource.create.return_value = created(
            {'kind': 'StatefulSet', 'metadata': {'name': 'web'},
             'status': {'replicas': 0, 'availableReplicas': 0}})

        out = io.StringIO()
        with redirect_stdout(out):
            create_from_yaml.main()

        status = printed(out.getvalue())
        self.assertEqual(0, status['available_replicas'])
        self.assertIn('update_revision', status)
        self.assertIsNone(status['update_revision'])

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_prints_the_metadata_of_types_without_status(
            self, mock_connect, mock_dynamic):
        self._configure('ConfigMap', 'kind: ConfigMap\n')
        resource = self._resource(mock_dynamic)
        resource.create.return_value = created(
            {'kind': 'ConfigMap', 'metadata': {'name': 'settings'}, 'data': {'a': 'b'}})

        out = io.StringIO()
        with redirect_stdout(out):
            create_from_yaml.main()

        metadata = printed(out.getvalue())
        self.assertEqual('settings', metadata['name'])
        self.assertIn('namespace', metadata)
        self.assertIsNone(metadata['namespace'])

    def _run_fallback(self, mock_dynamic):
        self._configure('StatefulSet', 'kind: StatefulSet\n')
        resource = self._resource(mock_dynamic)
        resource.create.return_value = created(
            {'kind': 'StatefulSet', 'metadata': {'name': 'web'},
             'status': {'replicas': 0}})
        out = io.StringIO()
        with redirect_stdout(out):
            create_from_yaml.main()  # must not exit: the resource exists
        resource.create.assert_called_once()
        return printed(out.getvalue())

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_prints_the_raw_status_when_the_model_is_missing(
            self, mock_connect, mock_dynamic):
        with patch.object(create_from_yaml, 'client', spec=['ApiClient']):
            self.assertEqual({'replicas': 0}, self._run_fallback(mock_dynamic))

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_prints_the_raw_status_when_conversion_fails(
            self, mock_connect, mock_dynamic):
        with patch('kubernetes.client.ApiClient._ApiClient__deserialize',
                   side_effect=ValueError('bad data')):
            self.assertEqual({'replicas': 0}, self._run_fallback(mock_dynamic))

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_exits_with_the_api_server_message(self, mock_connect, mock_dynamic):
        self._configure('Pod', POD_YAML)
        error = ConflictError(ApiException(status=409, reason='Conflict'))
        error.headers = {'Content-Type': 'application/json'}
        error.body = json.dumps({'message': 'pods "web" already exists'})
        self._resource(mock_dynamic).create.side_effect = error

        with self.assertLogs(create_from_yaml.log, 'ERROR') as logs, \
                redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            create_from_yaml.main()

        self.assertEqual(1, cm.exception.code)
        self.assertIn('pods "web" already exists', logs.output[0])

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_exits_when_the_cluster_does_not_serve_the_type(
            self, mock_connect, mock_dynamic):
        self._configure('Ingress', 'kind: Ingress\n')
        mock_dynamic.return_value.resources.get.side_effect = ResourceNotFoundError(
            'No matches found for {"api_version": "networking.k8s.io/v1", "kind": "Ingress"}')

        with self.assertLogs(create_from_yaml.log, 'ERROR') as logs, \
                self.assertRaises(SystemExit) as cm:
            create_from_yaml.main()

        self.assertEqual(1, cm.exception.code)
        self.assertIn('No matches found', logs.output[0])

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_exits_on_invalid_yaml(self, mock_connect, mock_dynamic):
        self._configure('Pod', 'metadata: [name: web\n')

        with self.assertLogs(create_from_yaml.log, 'ERROR'), \
                self.assertRaises(SystemExit) as cm:
            create_from_yaml.main()

        self.assertEqual(1, cm.exception.code)
        mock_dynamic.return_value.resources.get.return_value.create.assert_not_called()

    @patch('kubernetes.dynamic.DynamicClient')
    @patch.object(create_from_yaml.common, 'connect')
    def test_main_exits_on_an_unsupported_type(self, mock_connect, mock_dynamic):
        # This used to exit 0 without creating anything.
        self._configure('CronJob', 'kind: CronJob\n')

        with self.assertLogs(create_from_yaml.log, 'ERROR'), \
                self.assertRaises(SystemExit) as cm:
            create_from_yaml.main()

        self.assertEqual(1, cm.exception.code)
        mock_dynamic.assert_not_called()


if __name__ == '__main__':
    unittest.main()
