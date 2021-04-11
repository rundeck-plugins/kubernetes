#!/usr/bin/env python -u
import argparse
import sys
import os
import common
import logging


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

    [name, namespace, container] = common.get_core_node_parameter_list()
    common.log_pod_parameters(log, {'name': name, 'namespace': namespace, 'container_name': container})
    common.verify_pod_exists(name, namespace)

    source_file = os.environ.get('RD_FILE_COPY_FILE')
    destination_file = os.environ.get('RD_FILE_COPY_DESTINATION')

    # force print destination to avoid error with node-executor
    print(destination_file)

    log.debug("Copying file from %s to %s", source_file, destination_file)

    destination_path = os.path.dirname(destination_file)
    destination_file_name = os.path.basename(destination_file)

    common.copy_file(name, namespace, container, source_file, destination_path, destination_file_name)


if __name__ == '__main__':
    main()
