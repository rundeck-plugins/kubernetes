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

    source_file = os.environ.get('RD_FILE_COPY_FILE')
    destination_file = os.environ.get('RD_FILE_COPY_DESTINATION')
    shell = os.environ.get('RD_CONFIG_SHELL')

    log.debug("Copying file from %s to %s" % (source_file, destination_file))

    # Calling exec interactively.
    exec_command = [shell]
    resp = stream(api.connect_get_namespaced_pod_exec, name, namespace,
                  command=exec_command,
                  stderr=True, stdin=True,
                  stdout=True, tty=False,
                  _preload_content=False)

    file = open(source_file, "r")

    commands = []
    commands.append("cat <<'EOF' >" + destination_file + "\n")
    commands.append(file.read())
    commands.append("EOF\n")

    while resp.is_open():
        resp.update(timeout=1)
        if resp.peek_stdout():
            print("STDOUT: %s" % resp.read_stdout())
        if resp.peek_stderr():
            print("STDERR: %s" % resp.read_stderr())

        if commands:
            c = commands.pop(0)
            resp.write_stdin(c)
        else:
            break

    resp.close()


if __name__ == '__main__':
    main()
