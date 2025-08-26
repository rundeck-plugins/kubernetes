#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)


def main():

    common.connect()

    [name, namespace, container] = common.get_core_node_parameter_list()

    if not container:
        core_v1 = client.CoreV1Api()
        response = core_v1.read_namespaced_pod_status(
            name=name,
            namespace=namespace,
            pretty="True"
        )
        container = response.spec.containers[0].name

    common.log_pod_parameters(log, {'name': name, 'namespace': namespace, 'container_name': container})
    common.verify_pod_exists(name, namespace)

    shell = os.environ.get('RD_CONFIG_SHELL')

    if 'RD_EXEC_COMMAND' in os.environ:
        command = os.environ['RD_EXEC_COMMAND']
    else:
        command = os.environ['RD_CONFIG_COMMAND']

    log.debug("Command: %s ", command)

    environments_variables, temporary_files = common.handle_rundeck_environment_variables(
                                                  name=name,
                                                  namespace=namespace,
                                                  container=container
                                              )

    exec_command = environments_variables + [shell, '-c', command]

    # calling exec and wait for response.
    resp, error = common.run_interactive_command(name, namespace, container, exec_command)

    if error:
        log.error("error running script")
        sys.exit(1)

    if len(temporary_files) > 0:
        common.clean_up_temporary_files(
            name=name,
            namespace=namespace,
            container=container,
            files=temporary_files
        )


if __name__ == '__main__':
    main()
