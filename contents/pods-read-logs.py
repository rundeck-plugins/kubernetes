#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')
    data["container"] = os.environ.get('RD_NODE_DEFAULT_CONTAINER_NAME')

    common.connect()

    try:
        v1 = client.CoreV1Api()
        ret = v1.read_namespaced_pod_log(
            namespace=data["namespace"],
            name=data["name"],
            container=data["container"],
            _preload_content=False
        )
        print(ret.read())

    except ApiException as e:
        log.error("Exception error creating: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
