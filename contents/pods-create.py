#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client

from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException


common.log_info_to_stdout()
log = logging.getLogger('kubernetes-create-pod')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)


def create_pod(data):
    # split('=', 1) so a value containing '=' does not raise on unpacking, and
    # an entry without '=' is reported rather than raising a bare ValueError.
    labels = {}
    for entry in (data["labels"] or '').split(','):
        if not entry:
            continue
        if '=' not in entry:
            log.error("Labels must be key=value pairs separated by commas, got: %s", entry)
            sys.exit(1)
        key, value = entry.split('=', 1)
        labels[key] = value

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

    data = common.get_code_node_parameter_dictionary()
    common.log_pod_parameters(log, data)

    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["image"] = os.environ.get('RD_CONFIG_IMAGE')
    data["ports"] = os.environ.get('RD_CONFIG_PORTS')
    data["replicas"] = os.environ.get('RD_CONFIG_REPLICAS')
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

    if os.environ.get('RD_CONFIG_RESOURCES_LIMITS'):
        rl = os.environ.get('RD_CONFIG_RESOURCES_LIMITS')
        data["resources_limits"] = rl

    if os.environ.get('RD_CONFIG_WAITREADY'):
        data["waitready"] = os.environ.get('RD_CONFIG_WAITREADY')

    if os.environ.get('RD_CONFIG_IMAGEPULLSECRETS'):
        data["image_pull_secrets"] = os.environ.get('RD_CONFIG_IMAGEPULLSECRETS')

    pod = create_pod(data)

    try:
        resp = api.create_namespaced_pod(namespace=data['namespace'],
                                         body=pod,
                                         pretty="True")
    except ApiException:
        log.exception("Exception creating pod %s:", data['name'])
        sys.exit(1)

    # Report the outcome only once it is known. Announcing success before
    # checking the response could print both that the pod was created and that
    # it does not exist.
    if not resp:
        log.error("Pod %s was not created", data['name'])
        sys.exit(1)

    print("Pod Created successfully")


if __name__ == '__main__':
    main()
