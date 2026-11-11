#!/usr/bin/env python -u
import sys
import os
import common
import logging

from kubernetes import client
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-copy-file')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)


def main():

    common.connect()

    name, namespace, container = common.get_core_node_parameter_list()

    if not name:
        log.error("Pod name is not defined. Set RD_CONFIG_NAME or RD_NODE_DEFAULT_NAME.")
        sys.exit(1)

    if not container:
        try:
            core_v1 = client.CoreV1Api()
            response = core_v1.read_namespaced_pod_status(
                name=name,
                namespace=namespace,
                pretty="true"
            )
        except ApiException as e:
            log.error("Failed to read pod %s in namespace %s: %s", name, namespace, e.reason)
            sys.exit(1)

        if not response.spec.containers:
            log.error("Pod %s has no containers", name)
            sys.exit(1)

        container = response.spec.containers[0].name
    else:
        common.verify_pod_exists(name, namespace)

    common.log_pod_parameters(log, {'name': name, 'namespace': namespace, 'container_name': container})

    source_file = os.environ.get('RD_FILE_COPY_FILE')
    destination_file = os.environ.get('RD_FILE_COPY_DESTINATION')

    if not source_file:
        log.error("Source file is not defined. Set RD_FILE_COPY_FILE.")
        sys.exit(1)

    if not destination_file:
        log.error("Destination file is not defined. Set RD_FILE_COPY_DESTINATION.")
        sys.exit(1)

    # force print destination to avoid error with node-executor
    print(destination_file)

    log.debug("Copying file from %s to %s", source_file, destination_file)

    destination_path = os.path.dirname(destination_file)
    destination_file_name = os.path.basename(destination_file)

    try:
        common.copy_file(name, namespace, container, source_file, destination_path, destination_file_name)
    except Exception:
        log.exception("Failed to copy file to pod %s", name)
        sys.exit(1)


if __name__ == '__main__':
    main()
