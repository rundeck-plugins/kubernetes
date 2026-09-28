#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes.client.rest import ApiException

common.log_info_to_stdout()
log = logging.getLogger('kubernetes-delete-pod')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = common.get_code_node_parameter_dictionary()

    if not data["name"]:
        log.error("Pod name is not defined. Set RD_CONFIG_NAME or RD_NODE_DEFAULT_NAME.")
        sys.exit(1)

    common.connect()

    try:
        resp = common.delete_pod(data)
        if resp:
            print("Pod deleted successfully")
        else:
            # Already gone. Deleting is idempotent, so a cleanup job that runs
            # twice should not fail the second time.
            print("Pod %s not found; nothing to delete" % data["name"])
    except ApiException:
        log.exception("Exception deleting pod %s:", data["name"])
        sys.exit(1)


if __name__ == '__main__':
    main()
