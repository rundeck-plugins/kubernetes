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

from unittest.mock import patch

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


class TestCreateJobObjectSelectors(unittest.TestCase):
    """Kubernetes generates a Job's selector unless manualSelector is set, so
    the selectors option is ignored with a warning instead of being sent."""

    def test_ignores_selectors_with_a_warning(self):
        with self.assertLogs('kubernetes-model-source', level='WARNING') as logs:
            job = job_create.create_job_object(job_data(
                labels='app=sel', selectors='app=sel'))

        self.assertEqual(1, len(logs.records))
        self.assertIn('Selectors are ignored', logs.records[0].getMessage())
        self.assertIsNone(job.spec.selector)
        self.assertIsNone(job.spec.manual_selector)
        self.assertEqual({'app': 'sel'}, job.spec.template.metadata.labels)

    def test_no_warning_without_selectors(self):
        with self.assertNoLogs('kubernetes-model-source', level='WARNING'):
            job = job_create.create_job_object(job_data(labels='app=sel'))

        self.assertIsNone(job.spec.selector)
        self.assertEqual({'app': 'sel'}, job.metadata.labels)

    def test_main_creates_the_job_when_selectors_are_set(self):
        env = {
            'RD_CONFIG_API_VERSION': 'batch/v1',
            'RD_CONFIG_NAME': 'my-job',
            'RD_CONFIG_NAMESPACE': 'default',
            'RD_CONFIG_CONTAINER_NAME': 'app',
            'RD_CONFIG_CONTAINER_IMAGE': 'busybox',
            'RD_CONFIG_IMAGE_PULL_POLICY': 'IfNotPresent',
            'RD_CONFIG_JOB_RESTART_POLICY': 'Never',
            'RD_CONFIG_SELECTORS': 'app=sel',
        }
        with patch.dict(os.environ, env), \
                patch.object(job_create.common, 'connect'), \
                patch.object(job_create.client, 'BatchV1Api') as batch, \
                self.assertLogs('kubernetes-model-source', level='WARNING'):
            job_create.main()

        create = batch.return_value.create_namespaced_job
        create.assert_called_once()
        self.assertEqual('default', create.call_args.kwargs['namespace'])
        self.assertIsNone(create.call_args.kwargs['body'].spec.selector)


if __name__ == '__main__':
    unittest.main()
