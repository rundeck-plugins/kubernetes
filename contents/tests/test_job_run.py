"""
Unit tests for job-run.py.

job-run.py has a hyphenated filename, so it is loaded with importlib. It does
"import common", which resolves through the inserted sys.path to a module object
distinct from contents.common, so patches target job_run.common.
"""

import importlib
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from kubernetes import client


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

job_run = importlib.import_module('job-run')

UID = '732f9d19-441f-471b-acad-edc2c3731859'
GENERATED = {
    'controller-uid': UID,
    'job-name': 'my-job',
    'batch.kubernetes.io/controller-uid': UID,
    'batch.kubernetes.io/job-name': 'my-job',
}


def finished_job(job_labels, template_labels, template_annotations=None):
    return client.V1Job(
        api_version='batch/v1',
        kind='Job',
        metadata=client.V1ObjectMeta(name='my-job', namespace='default', uid=UID,
                                     resource_version='42', labels=job_labels),
        spec=client.V1JobSpec(
            selector=client.V1LabelSelector(
                match_labels={'batch.kubernetes.io/controller-uid': UID}),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=template_labels,
                                             annotations=template_annotations),
                spec=client.V1PodSpec(
                    restart_policy='Never',
                    containers=[client.V1Container(name='app', image='busybox')]))),
        status=client.V1JobStatus(succeeded=1))


class TestJobRunMain(unittest.TestCase):

    def setUp(self):
        os.environ.clear()
        os.environ.update({
            'RD_CONFIG_NAME': 'my-job',
            'RD_CONFIG_NAMESPACE': 'default',
        })

    def rerun(self, job):
        """Run main() against the Job and return the Job it creates."""
        with patch.object(job_run.client, 'BatchV1Api') as api_class, \
                patch.object(job_run.common, 'connect'), \
                redirect_stdout(io.StringIO()):
            api_class.return_value.read_namespaced_job.return_value = job
            api_class.return_value.delete_namespaced_job.return_value = {}
            job_run.main()

        return api_class.return_value.create_namespaced_job.call_args.kwargs['body']

    def test_main_keeps_the_labels_and_annotations_of_the_pod_template(self):
        created = self.rerun(finished_job(
            job_labels={'team': 'a'},
            template_labels=dict(GENERATED, team='a'),
            template_annotations={'example.com/inject': 'true'}))

        self.assertEqual({'team': 'a'}, created.spec.template.metadata.labels)
        self.assertEqual({'example.com/inject': 'true'},
                         created.spec.template.metadata.annotations)

    def test_main_removes_the_generated_labels_from_the_job_too(self):
        # A Job created without labels gets the labels of its pod template.
        created = self.rerun(finished_job(
            job_labels=dict(GENERATED), template_labels=dict(GENERATED)))

        self.assertEqual({}, created.metadata.labels)
        self.assertEqual({}, created.spec.template.metadata.labels)
        self.assertIsNone(created.spec.selector)

    def test_main_runs_a_job_whose_pod_template_has_no_metadata(self):
        job = finished_job(job_labels=None, template_labels=None)
        job.spec.template.metadata = None

        created = self.rerun(job)

        self.assertIsNone(created.spec.template.metadata)


if __name__ == '__main__':
    unittest.main()
