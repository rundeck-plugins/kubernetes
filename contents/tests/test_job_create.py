"""
Unit tests for job-create.py.

job-create.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common.
"""

import importlib
import os
import sys
import unittest

import yaml


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

job_create = importlib.import_module('job-create')


def job_data(**extra):
    data = {
        'api_version': 'batch/v1',
        'name': 'my-job',
        'namespace': 'default',
        'container_name': 'app',
        'container_image': 'busybox',
        'image_pull_policy': 'IfNotPresent',
        'job_restart_policy': 'Never',
    }
    data.update(extra)
    return data


class TestCreateJobObjectEnvFrom(unittest.TestCase):

    def test_reads_config_map_and_secret_references(self):
        job = job_create.create_job_object(job_data(env_from=(
            '- configMapRef:\n'
            '    name: settings\n'
            '- secretRef:\n'
            '    name: credentials\n'
            '    optional: true\n')))

        env_from = job.spec.template.spec.containers[0].env_from
        self.assertEqual('settings', env_from[0].config_map_ref.name)
        self.assertEqual('credentials', env_from[1].secret_ref.name)
        self.assertTrue(env_from[1].secret_ref.optional)

    def test_rejects_python_specific_yaml_tags(self):
        # env_from can come from a job option. Python tags such as this one are
        # what older PyYAML full_load turned into code execution on the server.
        with self.assertRaises(yaml.YAMLError):
            job_create.create_job_object(job_data(env_from='- !!python/tuple [a, b]\n'))


if __name__ == '__main__':
    unittest.main()
