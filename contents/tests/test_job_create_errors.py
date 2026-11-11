"""
Unit tests for job-create.py's main(): how it reports errors.

job-create.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common, so patches target job_create.common.
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

job_create = importlib.import_module('job-create')


class TestJobCreateMain(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    @patch.object(job_create.client, 'BatchV1Api')
    @patch.object(job_create.common, 'connect')
    def test_main_logs_a_wrongly_typed_option_and_exits(self, mock_connect, mock_api_class):
        # Kubernetes client 37 rejects the number while building the toleration
        # and raises a pydantic ValidationError (a ValueError). Older clients
        # send it, and the API server rejects it, as the mocked call does here.
        os.environ.update({
            'RD_CONFIG_API_VERSION': 'batch/v1',
            'RD_CONFIG_NAME': 'my-job',
            'RD_CONFIG_NAMESPACE': 'default',
            'RD_CONFIG_CONTAINER_NAME': 'app',
            'RD_CONFIG_CONTAINER_IMAGE': 'busybox',
            'RD_CONFIG_JOB_RESTART_POLICY': 'Never',
            'RD_CONFIG_TOLERATIONS': '- key: dedicated\n  operator: Equal\n  value: 1\n',
        })
        mock_api_class.return_value.create_namespaced_job.side_effect = ApiException(
            status=400, reason='Bad Request')

        with redirect_stdout(io.StringIO()), \
                self.assertLogs('kubernetes-model-source', level='ERROR') as logs, \
                self.assertRaises(SystemExit) as cm:
            job_create.main()

        self.assertEqual(1, cm.exception.code)
        self.assertIn('Exception creating job', logs.output[0])


if __name__ == '__main__':
    unittest.main()
