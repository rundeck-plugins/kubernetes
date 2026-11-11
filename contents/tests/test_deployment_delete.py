"""
Unit tests for deployment-delete.py.

deployment-delete.py has a hyphenated filename, so it is loaded with importlib.
It does "import common", which resolves through the inserted sys.path to a
module object distinct from contents.common.
"""

import importlib
import io
import json
import os
import sys
import unittest

from contextlib import redirect_stdout
from unittest.mock import MagicMock

from kubernetes import client


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

deployment_delete = importlib.import_module('deployment-delete')


DATA = {'name': 'web', 'namespace': 'default'}


class TestDeploymentDelete(unittest.TestCase):

    def delete_with_response(self, response):
        api = MagicMock()
        api.delete_namespaced_deployment.return_value = response
        out = io.StringIO()
        with redirect_stdout(out):
            deployment_delete.delete_deployment(api, DATA)
        api.delete_namespaced_deployment.assert_called_once()
        return out.getvalue()

    def test_prints_status_of_a_dict_response(self):
        # kubernetes 37 declares the response as "object" and returns the
        # decoded JSON, here the Deployment being deleted in the foreground.
        out = self.delete_with_response({
            'kind': 'Deployment',
            'metadata': {'name': 'web'},
            'status': {'replicas': 1, 'readyReplicas': 1},
        })
        self.assertEqual({'replicas': 1, 'readyReplicas': 1}, json.loads(out))

    def test_prints_status_of_a_v1status_response(self):
        # kubernetes 36 returns a V1Status.
        out = self.delete_with_response(client.V1Status(status='Success'))
        self.assertEqual('Success', json.loads(out))


if __name__ == '__main__':
    unittest.main()
