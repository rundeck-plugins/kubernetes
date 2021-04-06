#!/usr/bin/env python -u
import argparse
import sys
import os
import common
import logging


from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)

parser = argparse.ArgumentParser(
    description='Execute a command string in the container.')
parser.add_argument('pod', help='Pod')

args = parser.parse_args()


def main():

    common.connect()
    api = core_v1_api.CoreV1Api()

    name = os.environ.get('RD_CONFIG_NAME', os.environ.get('RD_NODE_DEFAULT_NAME'))
    namespace = os.environ.get('RD_CONFIG_NAMESPACE', os.environ.get('RD_NODE_DEFAULT_NAMESPACE', 'default'))
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
    print(destination_file)

    log.debug("Copying file from %s to %s" % (source_file, destination_file))

    destination_path = os.path.dirname(destination_file)
    destination_file_name = os.path.basename(destination_file)

    common.copy_file(name, namespace, container, source_file, destination_path, destination_file_name)


if __name__ == '__main__':
    main()
