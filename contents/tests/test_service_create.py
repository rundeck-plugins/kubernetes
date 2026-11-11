"""
Unit tests for service-create.py.

service-create.py has a hyphenated filename, so it is loaded with importlib. It
does "import common", which resolves through the inserted sys.path to a module
object distinct from contents.common, so patches target service_create.common.
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

service_create = importlib.import_module('service-create')


class TestServiceCreateMain(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    @patch.object(service_create.client, 'CoreV1Api')
    @patch.object(service_create.common, 'connect')
    def test_main_logs_a_wrongly_typed_option_and_exits(self, mock_connect, mock_api_class):
        # Kubernetes client 37 rejects the number while building the port and
        # raises a pydantic ValidationError (a ValueError). Older clients send
        # it, and the API server rejects it, as the mocked call does here.
        os.environ.update({
            'RD_CONFIG_API_VERSION': 'v1',
            'RD_CONFIG_NAME': 'web',
            'RD_CONFIG_NAMESPACE': 'default',
            'RD_CONFIG_TYPE': 'ClusterIP',
            'RD_CONFIG_LABELS': 'app=web',
            'RD_CONFIG_SELECTORS': 'app=web',
            'RD_CONFIG_PORTS': '- port: 80\n  name: 80\n  protocol: TCP\n',
        })
        mock_api_class.return_value.create_namespaced_service.side_effect = ApiException(
            status=400, reason='Bad Request')

        with redirect_stdout(io.StringIO()), \
                self.assertLogs('kubernetes-service-create', level='ERROR') as logs, \
                self.assertRaises(SystemExit) as cm:
            service_create.main()

        self.assertEqual(1, cm.exception.code)
        self.assertIn('Exception when calling create_namespaced_service', logs.output[0])


if __name__ == '__main__':
    unittest.main()
