#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    common.connect()

    data = {}
    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    try:

        k8s_client = client.BatchV1Api()
        job = k8s_client.read_namespaced_job(
            name=data["name"],
            namespace=data["namespace"]
        )
        job.metadata.creation_timestamp = None
        job.metadata.uid = None
        job.metadata.resource_version = None
        job.status = None
        job.spec.selector = None
        job.spec.template.metadata = None

        body = client.V1DeleteOptions()
        pretty = 'pretty_example'

        api_response = k8s_client.delete_namespaced_job(
            name=data["name"],
            namespace=data["namespace"],
            body=body,
            pretty=pretty
        )

        print("Job deleted. status='%s'" % str(api_response.status))

        api_response = k8s_client.create_namespaced_job(
            body=job,
            namespace=data["namespace"]
        )
        print("Job created. status='%s'" % str(api_response.status))

    except ApiException as e:
        log.error("Exception creating job: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
