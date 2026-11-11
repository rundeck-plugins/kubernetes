"""
Unit tests for deployment-create.py.

deployment-create.py has a hyphenated filename, so it is loaded with importlib.
It does "import common", which resolves through the inserted sys.path to a
module object distinct from contents.common, so patches target
deployment_create.common.
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

deployment_create = importlib.import_module('deployment-create')


class TestDeploymentCreateMain(unittest.TestCase):

    def setUp(self):
        os.environ.clear()
        os.environ.update({
            'RD_CONFIG_API_VERSION': 'apps/v1',
            'RD_CONFIG_NAME': 'web',
            'RD_CONFIG_CONTAINER_NAME': 'app',
            'RD_CONFIG_IMAGE': 'nginx:latest',
            'RD_CONFIG_REPLICAS': '1',
            'RD_CONFIG_NAMESPACE': 'default',
            'RD_CONFIG_LABELS': 'app=web',
        })

    @patch.object(deployment_create.client, 'AppsV1Api')
    @patch.object(deployment_create.common, 'connect')
    def test_main_creates_the_deployment(self, mock_connect, mock_api_class):
        mock_api_class.return_value.create_namespaced_deployment.return_value = MagicMock()

        with redirect_stdout(io.StringIO()):
            deployment_create.main()

        kwargs = mock_api_class.return_value.create_namespaced_deployment.call_args[1]
        self.assertEqual('default', kwargs['namespace'])
        self.assertEqual('web', kwargs['body'].metadata.name)

    @patch.object(deployment_create.client, 'AppsV1Api')
    @patch.object(deployment_create.common, 'connect')
    def test_main_logs_a_wrongly_typed_option_and_exits(self, mock_connect, mock_api_class):
        # Kubernetes client 37 rejects the string while building the volume
        # mount and raises a pydantic ValidationError (a ValueError). Older
        # clients send it, and the API server rejects it, as the mocked call
        # does here.
        os.environ['RD_CONFIG_VOLUME_MOUNTS'] = 'name: data\nmountPath: /data\nreadOnly: "true"\n'
        mock_api_class.return_value.create_namespaced_deployment.side_effect = ApiException(
            status=400, reason='Bad Request')

        with redirect_stdout(io.StringIO()), \
                self.assertLogs('kubernetes-model-source', level='ERROR') as logs, \
                self.assertRaises(SystemExit) as cm:
            deployment_create.main()

        self.assertEqual(1, cm.exception.code)
        self.assertIn('Exception creating deployment', logs.output[0])


if __name__ == '__main__':
    unittest.main()
