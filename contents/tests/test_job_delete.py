"""
Unit tests for job-delete.py.

job-delete.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common, so patches target job_delete.common.
"""

import importlib
import logging
import os
import sys
import unittest

from unittest.mock import MagicMock, patch

from kubernetes import client


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

job_delete = importlib.import_module('job-delete')


ENV = {'RD_CONFIG_NAME': 'my-job', 'RD_CONFIG_NAMESPACE': 'default'}


class TestJobDelete(unittest.TestCase):

    def setUp(self):
        job_delete.log.setLevel(logging.NOTSET)

    def tearDown(self):
        job_delete.log.setLevel(logging.NOTSET)

    def run_main(self, response, env=ENV):
        """Run main() with delete_namespaced_job returning response, and
        return the BatchV1Api stand-in."""
        core = MagicMock()
        core.list_namespaced_pod.return_value.items = []
        batch = MagicMock()
        batch.delete_namespaced_job.return_value = response
        with patch.dict(os.environ, env, clear=True), \
                patch.object(job_delete.common, 'connect'), \
                patch.object(job_delete.client, 'CoreV1Api', return_value=core), \
                patch.object(job_delete.client, 'BatchV1Api', return_value=batch):
            job_delete.main()
        return batch

    def test_deletes_job_when_the_response_is_a_dict(self):
        # kubernetes 37 declares the response as "object" and returns the
        # decoded JSON. The status is formatted for the debug log even when
        # debug is off, so this must not fail either way.
        batch = self.run_main({'kind': 'Status', 'status': 'Success'})
        batch.delete_namespaced_job.assert_called_once()

    def test_logs_status_of_a_dict_response_when_debug_is_on(self):
        env = dict(ENV, RD_CONFIG_DEBUG='true')
        with self.assertLogs(job_delete.log, level='DEBUG') as logs:
            self.run_main({'kind': 'Status', 'status': 'Success'}, env)
        self.assertIn('DEBUG:kubernetes-service-delete:"Success"', logs.output)

    def test_logs_status_of_a_v1status_response_when_debug_is_on(self):
        # kubernetes 36 returns a V1Status.
        env = dict(ENV, RD_CONFIG_DEBUG='true')
        with self.assertLogs(job_delete.log, level='DEBUG') as logs:
            self.run_main(client.V1Status(status='Success'), env)
        self.assertIn('DEBUG:kubernetes-service-delete:"Success"', logs.output)


if __name__ == '__main__':
    unittest.main()
