#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client
from kubernetes.client.rest import ApiException


common.log_info_to_stdout()
log = logging.getLogger('kubernetes-pod-describe')


def main():

    # get_core_node_parameter_list already prefers the step's own setting over
    # the node's, for both name and namespace, and falls back to the "default"
    # namespace last. Resolving name here but not namespace would lose the
    # node's namespace whenever the step named a pod without one.
    pod_name, namespace, _ = common.get_core_node_parameter_list()

    if not pod_name:
        log.error("Pod name is not defined. Set RD_CONFIG_NAME or RD_NODE_DEFAULT_NAME.")
        sys.exit(1)

    common.connect()

    try:
        api = client.CoreV1Api()

        api_response = api.read_namespaced_pod(
            name=pod_name,
            namespace=namespace)

        print(common.parseJson(api_response.status))

    except ApiException:
        log.exception("Exception describing pod %s:", pod_name)
        sys.exit(1)


if __name__ == '__main__':
    main()
