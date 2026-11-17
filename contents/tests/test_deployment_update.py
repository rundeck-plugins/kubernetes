"""
Unit tests for deployment-update.py.

deployment-update.py has a hyphenated filename, so it is loaded with importlib.
It does "import common", which resolves through the inserted sys.path to a
module object distinct from contents.common, so patches target
deployment_update.common.
"""

import importlib
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from kubernetes.client.rest import ApiException


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

deployment_update = importlib.import_module('deployment-update')


class TestDeploymentUpdateMain(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    @patch.object(deployment_update.client, 'AppsV1Api')
    @patch.object(deployment_update.common, 'connect')
    def test_main_logs_a_wrongly_typed_option_and_exits(self, mock_connect, mock_api_class):
        # Kubernetes client 37 rejects the string while building the probe and
        # raises a pydantic ValidationError (a ValueError). Older clients send
        # it, and the API server rejects it, as the mocked call does here.
        os.environ.update({
            'RD_CONFIG_API_VERSION': 'apps/v1',
            'RD_CONFIG_NAME': 'web',
            'RD_CONFIG_CONTAINER_NAME': 'app',
            'RD_CONFIG_IMAGE': 'nginx:latest',
            'RD_CONFIG_REPLICAS': '1',
            'RD_CONFIG_NAMESPACE': 'default',
            'RD_CONFIG_READINESS_PROBE': 'exec:\n  command: cat /tmp/ready\n',
        })
        mock_api_class.return_value.patch_namespaced_deployment.side_effect = ApiException(
            status=400, reason='Bad Request')

        with redirect_stdout(io.StringIO()), \
                self.assertLogs('kubernetes-model-source', level='ERROR') as logs, \
                self.assertRaises(SystemExit) as cm:
            deployment_update.main()

        self.assertEqual(1, cm.exception.code)
        self.assertIn('Exception updating deployment', logs.output[0])

    def update(self, **options):
        """Run main() with the options and return the Deployment it sends."""
        os.environ.update({
            'RD_CONFIG_API_VERSION': 'apps/v1',
            'RD_CONFIG_NAME': 'web',
            'RD_CONFIG_CONTAINER_NAME': 'app',
            'RD_CONFIG_IMAGE': 'nginx:latest',
            'RD_CONFIG_REPLICAS': '1',
            'RD_CONFIG_NAMESPACE': 'default',
        })
        os.environ.update(options)

        with patch.object(deployment_update.client, 'AppsV1Api') as api_class, \
                patch.object(deployment_update.common, 'connect'), \
                redirect_stdout(io.StringIO()):
            deployment_update.main()

        patch_call = api_class.return_value.patch_namespaced_deployment
        return patch_call.call_args.kwargs['body']

    def test_main_sends_the_resources_limits(self):
        deployment = self.update(RD_CONFIG_RESOURCES_REQUESTS='cpu=100m',
                                 RD_CONFIG_RESOURCES_LIMITS='cpu=500m,memory=256Mi')

        resources = deployment.spec.template.spec.containers[0].resources
        self.assertEqual({'cpu': '100m'}, resources.requests)
        self.assertEqual({'cpu': '500m', 'memory': '256Mi'}, resources.limits)

    def test_main_accepts_an_environment_value_that_contains_an_equals_sign(self):
        deployment = self.update(RD_CONFIG_ENVIRONMENTS='JAVA_OPTS=-Dfoo=bar\nPLAIN=1')

        env = deployment.spec.template.spec.containers[0].env
        self.assertEqual({'JAVA_OPTS': '-Dfoo=bar', 'PLAIN': '1'},
                         {e.name: e.value for e in env})


if __name__ == '__main__':
    unittest.main()
