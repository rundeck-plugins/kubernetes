#!/usr/bin/env python -u
import logging
import sys
import os
import tempfile

import common

from kubernetes import client
from kubernetes.client.rest import ApiException

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-run-script')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)


def remove_script(name, namespace, container, full_path):
    """Delete the copied script from the container. Returns False if rm
    reported an error."""
    rm_command = ["rm", full_path]

    log.debug("removing file %s", rm_command)
    resp = common.run_command(name=name,
                              namespace=namespace,
                              container=container,
                              command=rm_command
                              )

    if resp.peek_stdout():
        log.debug(resp.read_stdout())

    if resp.peek_stderr():
        log.debug(resp.read_stderr())
        return False

    return True


def main():
    common.connect()
    api = client.CoreV1Api()

    name, namespace, container = common.get_core_node_parameter_list()

    if not name:
        log.error("Pod name is not defined. Set RD_CONFIG_NAME or RD_NODE_DEFAULT_NAME.")
        sys.exit(1)

    common.verify_pod_exists(name, namespace)

    delete_on_fail = os.environ.get('RD_CONFIG_DELETEONFAIL') == 'true'

    if not container:
        response = api.read_namespaced_pod_status(
            name=name,
            namespace=namespace,
            pretty="True"
        )

        if response.spec.containers:
            container = response.spec.containers[0].name
        else:
            log.error("Container not found")
            sys.exit(1)

    common.log_pod_parameters(log, {'name': name, 'namespace': namespace, 'container_name': container})

    script = os.environ.get('RD_CONFIG_SCRIPT')

    if not script:
        log.error("No script provided. Set RD_CONFIG_SCRIPT.")
        sys.exit(1)

    script = script.encode('utf-8')

    log.debug("--------------------------")
    log.debug("Pod Name:  %s", name)
    log.debug("Namespace: %s", namespace)
    log.debug("Container: %s", container)
    log.debug("--------------------------")

    invocation = os.environ.get('RD_CONFIG_INVOCATION', '/bin/bash')
    destination_path = os.environ.get('RD_NODE_FILE_COPY_DESTINATION_DIR', '/tmp')

    temp = tempfile.NamedTemporaryFile()
    destination_file_name = os.path.basename(temp.name)
    full_path = os.path.join(destination_path, destination_file_name)

    try:
        temp.write(script)
        temp.seek(0)

        log.debug("copying script from %s to %s", temp.name, full_path)

        common.copy_file(name=name,
                         namespace=namespace,
                         container=container,
                         source_file=temp.name,
                         destination_path=destination_path,
                         destination_file_name=destination_file_name
                         )

    finally:
        temp.close()

    # The script can hold values expanded from job options, such as passwords,
    # so remove it from the container when a later step fails too.
    pod_deleted = False
    try:
        permissions_command = ["chmod", "+x", full_path]

        log.debug("setting permissions %s", permissions_command)
        resp = common.run_command(name=name,
                                  namespace=namespace,
                                  container=container,
                                  command=permissions_command
                                  )

        if resp.peek_stdout():
            print(resp.read_stdout())

        if resp.peek_stderr():
            print(resp.read_stderr())
            sys.exit(1)

        # calling exec and wait for response.
        exec_command = invocation.split(" ")
        exec_command.append(full_path)

        if 'RD_CONFIG_ARGUMENTS' in os.environ:
            arguments = os.environ.get('RD_CONFIG_ARGUMENTS')
            for arg in arguments.split(" "):
                exec_command.append(arg)

        log.debug("running script %s", exec_command)

        resp, error = common.run_interactive_command(name=name,
                                                     namespace=namespace,
                                                     container=container,
                                                     command=exec_command
                                                     )
        if error:
            log.error("error running script")

            if delete_on_fail:
                log.info("removing POD on fail")
                data = {"name": name, "namespace": namespace}
                # Cleanup runs because the script already failed. Report a cleanup
                # failure without letting it mask the failure that caused it.
                try:
                    common.delete_pod(data)
                    pod_deleted = True
                    log.info("POD deleted")
                except ApiException:
                    log.exception("Failed to remove POD %s after script failure:", name)
            sys.exit(1)
    except BaseException:
        # Also reached through sys.exit(1) above. Removing the script must not
        # replace the failure that got us here.
        if not pod_deleted:
            try:
                remove_script(name, namespace, container, full_path)
            except Exception:
                log.exception("Failed to remove %s from the container:", full_path)
        raise

    if not remove_script(name, namespace, container, full_path):
        sys.exit(1)


if __name__ == '__main__':
    main()
