#!/usr/bin/env python -u
import argparse
import logging
import sys
import os
import common
import tarfile
import logging


from kubernetes.client.apis import core_v1_api
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from tempfile import TemporaryFile

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

    name = os.environ.get('RD_NODE_DEFAULT_NAME')
    namespace = os.environ.get('RD_NODE_DEFAULT_NAMESPACE')
    container = os.environ.get('RD_NODE_DEFAULT_CONTAINER_NAME')

    log.debug("--------------------------")
    log.debug("Pod Name:  %s" % name)
    log.debug("Namespace: %s " % namespace)
    log.debug("Container: %s " % container)
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

    #force print destination to avoid error with node-executor
    print destination_file

    log.debug("Copying file from %s to %s" % (source_file, destination_file))

    destination_path = os.path.dirname(destination_file)
    destination_file_name = os.path.basename(destination_file)

    # Copying file client -> pod
    exec_command = ['tar', 'xvf', '-', '-C', '/']
    resp = stream(api.connect_get_namespaced_pod_exec, name, 'default',
                  command=exec_command,
                  container=container,
                  stderr=True, stdin=True,
                  stdout=True, tty=False,
                  _preload_content=False)

    with TemporaryFile() as tar_buffer:
        with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
            tar.add(name=source_file, arcname=destination_path + "/" + destination_file_name)

        tar_buffer.seek(0)
        commands = []
        commands.append(tar_buffer.read())

        while resp.is_open():
            resp.update(timeout=1)
            if resp.peek_stdout():
                print("STDOUT: %s" % resp.read_stdout())
            if resp.peek_stderr():
                print("STDERR: %s" % resp.read_stderr())
            if commands:
                c = commands.pop(0)
                # print("Running command... %s\n" % c)
                resp.write_stdin(c)
            else:
                break
        resp.close()


if __name__ == '__main__':
    main()
