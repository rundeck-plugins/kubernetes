#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException
from kubernetes import client

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)

def main():

    common.connect()

    api = core_v1_api.CoreV1Api()
    container = None
    name = None
    namespace = None

    name = os.environ.get('RD_CONFIG_NAME', os.environ.get('RD_NODE_DEFAULT_NAME'))
    namespace = os.environ.get('RD_CONFIG_NAMESPACE', os.environ.get('RD_NODE_DEFAULT_NAMESPACE', 'default'))

    if 'RD_NODE_DEFAULT_CONTAINER_NAME' in os.environ:
        container = os.environ.get('RD_NODE_DEFAULT_CONTAINER_NAME')
    else:
        core_v1 = client.CoreV1Api()
        response = core_v1.read_namespaced_pod_status(
            name=name,
            namespace=namespace,
            pretty="True"
        )
        container = response.spec.containers[0].name

    log.debug("--------------------------")
    log.debug("Pod Name:  %s", name)
    log.debug("Namespace: %s", namespace)
    log.debug("Container: %s", container)
    log.debug("--------------------------")

    resp = None
    try:
        resp = api.read_namespaced_pod(name=name,
                                       namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            log.exception("Unknown error:")
            exit(1)

    if not resp:
        log.error("Pod %s does not exist", name)
        exit(1)

    shell = os.environ.get('RD_CONFIG_SHELL')

    if 'RD_EXEC_COMMAND' in os.environ:
        command = os.environ['RD_EXEC_COMMAND']
    else:
        command = os.environ['RD_CONFIG_COMMAND']

    log.debug("Command: %s ", command)

    # calling exec and wait for response.
    exec_command = [
        shell,
        '-c',
        command]

    resp, error = common.run_interactive_command(name, namespace, container, exec_command)

    if error:
        log.error("error running script")
        sys.exit(1)


if __name__ == '__main__':
    main()
