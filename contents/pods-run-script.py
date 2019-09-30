#!/usr/bin/env python -u
import logging
import sys
import os
import tempfile

import common

from kubernetes.client.apis import core_v1_api
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
    namespace = os.environ.get('RD_CONFIG_NAMESPACE')
    name = os.environ.get('RD_CONFIG_NAME')

    log.debug("--------------------------")
    log.debug("Pod Name:  %s" % name)
    log.debug("Namespace: %s " % namespace)
    log.debug("--------------------------")

    delete_on_fail = False
    if os.environ.get('RD_CONFIG_DELETEONFAIL') == 'true':
        delete_on_fail = True

    resp = None
    try:
        resp = api.read_namespaced_pod(name=name,
                                       namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            log.error("Unknown error: %s" % e)
            exit(1)

    if not resp:
        log.error("Pod %s does not exits." % name)
        exit(1)

    core_v1 = client.CoreV1Api()
    response = core_v1.read_namespaced_pod_status(
        name=name,
        namespace=namespace,
        pretty="True"
    )

    if response.spec.containers:
        container = response.spec.containers[0].name
    else:
        log.error("Container not found")
        exit(1)

    script = os.environ.get('RD_CONFIG_SCRIPT')
    invocation = "/bin/bash"
    if 'RD_CONFIG_INVOCATION' in os.environ:
        invocation = os.environ.get('RD_CONFIG_INVOCATION')

    destination_path = "/tmp"

    if 'RD_NODE_FILE_COPY_DESTINATION_DIR' in os.environ:
        destination_path = os.environ.get('RD_NODE_FILE_COPY_DESTINATION_DIR')

    temp = tempfile.NamedTemporaryFile()
    destination_file_name = os.path.basename(temp.name)
    full_path = destination_path + "/" + destination_file_name

    try:
        temp.write(script)
        temp.seek(0)

        log.debug("coping script from %s to %s" % (temp.name,full_path))

        common.copy_file(name=name,
                         namespace=namespace,
                         container=container,
                         source_file=temp.name,
                         destination_path= destination_path,
                         destination_file_name=destination_file_name
                         )

    finally:
        temp.close()

    permissions_command = ["chmod", "+x", full_path]

    log.debug("setting permissions %s" % permissions_command)
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
        exec_command.append(arguments)

    log.debug("running script %s" % exec_command)

    resp, error = common.run_interactive_command(name=name,
                                          namespace=namespace,
                                          container=container,
                                          command=exec_command
                                          )
    if error:
        log.error("error running script")

        if delete_on_fail:
            log.info("removing POD on fail")
            data = {}
            data["name"] = name
            data["namespace"] = namespace
            common.delete_pod(api, data)

            log.info("POD deleted")
        sys.exit(1)

    rm_command = ["rm", full_path]

    log.debug("removing file %s" % rm_command)
    resp = common.run_command(name=name,
                              namespace=namespace,
                              container=container,
                              command=rm_command
                              )

    if resp.peek_stdout():
        log.debug(resp.read_stdout())

    if resp.peek_stderr():
        log.debug(resp.read_stderr())
        sys.exit(1)


if __name__ == '__main__':
    main()
