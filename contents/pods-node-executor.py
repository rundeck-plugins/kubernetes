#!/usr/bin/env python -u
import argparse
import logging
import sys
import os
import common

from kubernetes.client.apis import core_v1_api
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')

parser = argparse.ArgumentParser(
    description='Execute a command string in the container.')
parser.add_argument('pod', help='Pod')

args = parser.parse_args()


def main():

    common.connect()

    api = core_v1_api.CoreV1Api()

    name = args.pod
    namespace = os.environ.get('RD_NODE_DEFAULT_NAMESPACE')

    log.debug("--------------------------")
    log.debug("Pod Name:  %s" % name)
    log.debug("Namespace: %s " % namespace)
    log.debug("--------------------------")

    resp = None
    try:
        resp = api.read_namespaced_pod(name=name,
                                       namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            print("Unknown error: %s" % e)
            exit(1)

    if not resp:
        print("Pod %s does not exits." % name)
        exit(1)

    command = os.environ.get('RD_EXEC_COMMAND')
    shell = os.environ.get('RD_CONFIG_SHELL')

    log.debug("Command: %s " % command)

    # calling exec and wait for response.
    exec_command = [
        shell,
        '-c',
        command]

    # Calling exec interactively.
    resp = stream(api.connect_get_namespaced_pod_exec,
                  name=name,
                  namespace=namespace,
                  command=exec_command,
                  stderr=True,
                  stdin=True,
                  stdout=True,
                  tty=False,
                  _preload_content=False
                  )

    resp.run_forever()
    if resp.peek_stdout():
        print(resp.read_stdout())

    if resp.peek_stderr():
        print(resp.read_stderr())
        sys.exit(1)


if __name__ == '__main__':
    main()
