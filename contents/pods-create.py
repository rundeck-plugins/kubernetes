#!/usr/bin/env python -u
import argparse
import logging
import sys
import os
import common

from kubernetes import client

from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr,
                    level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-create-pod')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)


def create_pod(data):
    labels_array = data["labels"].split(',')
    labels = dict(s.split('=') for s in labels_array)

    metadata = client.V1ObjectMeta(labels=labels,
                                   namespace=data["namespace"],
                                   name=data["name"])

    template_spec = common.create_pod_template_spec(data)

    pod = client.V1Pod(
        api_version=data["api_version"],
        kind="Pod",
        metadata=metadata,
        spec=template_spec
    )

    return pod




def main():

    common.connect()

    api = core_v1_api.CoreV1Api()

    namespace = os.environ.get('RD_CONFIG_NAMESPACE')
    name = os.environ.get('RD_CONFIG_NAME')
    container = os.environ.get('RD_CONFIG_CONTAINER_NAME')

    log.debug("--------------------------")
    log.debug("Pod Name:  %s", name)
    log.debug("Namespace: %s", namespace)
    log.debug("Container: %s", container)
    log.debug("--------------------------")

    data = {}

    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["container_name"] = os.environ.get('RD_CONFIG_CONTAINER_NAME')
    data["image"] = os.environ.get('RD_CONFIG_IMAGE')
    data["ports"] = os.environ.get('RD_CONFIG_PORTS')
    data["replicas"] = os.environ.get('RD_CONFIG_REPLICAS')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')
    data["labels"] = os.environ.get('RD_CONFIG_LABELS')
    if os.environ.get('RD_CONFIG_ENVIRONMENTS'):
        data["environments"] = os.environ.get('RD_CONFIG_ENVIRONMENTS')

    if os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS'):
        evs = os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS')
        data["environments_secrets"] = evs

    if os.environ.get('RD_CONFIG_LIVENESS_PROBE'):
        data["liveness_probe"] = os.environ.get('RD_CONFIG_LIVENESS_PROBE')

    if os.environ.get('RD_CONFIG_READINESS_PROBE'):
        data["readiness_probe"] = os.environ.get('RD_CONFIG_READINESS_PROBE')

    if os.environ.get('RD_CONFIG_VOLUME_MOUNTS'):
        data["volume_mounts"] = os.environ.get('RD_CONFIG_VOLUME_MOUNTS')

    if os.environ.get('RD_CONFIG_VOLUMES'):
        data["volumes"] = os.environ.get('RD_CONFIG_VOLUMES')

    if os.environ.get('RD_CONFIG_CONTAINER_COMMAND'):
        cc = os.environ.get('RD_CONFIG_CONTAINER_COMMAND')
        data["container_command"] = cc

    if os.environ.get('RD_CONFIG_CONTAINER_ARGS'):
        data["container_args"] = os.environ.get('RD_CONFIG_CONTAINER_ARGS')

    if os.environ.get('RD_CONFIG_RESOURCES_REQUESTS'):
        rr = os.environ.get('RD_CONFIG_RESOURCES_REQUESTS')
        data["resources_requests"] = rr

    if os.environ.get('RD_CONFIG_WAITREADY'):
        data["waitready"] = os.environ.get('RD_CONFIG_WAITREADY')

    if os.environ.get('RD_CONFIG_IMAGEPULLSECRETS'):
        data["image_pull_secrets"] = os.environ.get('RD_CONFIG_IMAGEPULLSECRETS')

    pod = create_pod(data)
    resp = None
    try:
        resp = api.create_namespaced_pod(namespace=namespace,
                                         body=pod,
                                         pretty="True")

        print("Pod Created successfully")

    except ApiException:
        log.exception("Exception creating pod:")
        exit(1)

    if not resp:
        print("Pod %s does not exist" % name)
        exit(1)


if __name__ == '__main__':
    main()
