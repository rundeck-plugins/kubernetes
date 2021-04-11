#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes.client.rest import ApiException

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-delete-pod')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = common.get_code_node_parameter_dictionary()

    common.connect()

    try:
        common.delete_pod(data)
        print("Pod deleted successfully")
    except ApiException:
        log.exception("Exception deleting deployment:")
        sys.exit(1)


if __name__ == '__main__':
    main()
