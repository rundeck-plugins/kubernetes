#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client
from kubernetes.client.rest import ApiException

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-node-executor')

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

    shell = os.environ.get('RD_CONFIG_SHELL')

    command = os.environ.get('RD_EXEC_COMMAND') or os.environ.get('RD_CONFIG_COMMAND')
    if not command:
        log.error("No command specified. Set RD_EXEC_COMMAND or RD_CONFIG_COMMAND.")
        sys.exit(1)

    log.debug("Command: %s ", command)

    # calling exec and wait for response.
    exec_command = [
        shell,
        '-c',
        command]

    _, error = common.run_interactive_command(name, namespace, container, exec_command)

    if error:
        log.error("error running script")
        sys.exit(1)


if __name__ == '__main__':
    main()
