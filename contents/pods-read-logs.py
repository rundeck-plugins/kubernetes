#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client
from kubernetes.client.rest import ApiException
from kubernetes import watch

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format='%(message)s')
log = logging.getLogger('kubernetes-model-source')


def main():
    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')
    data["container"] = os.environ.get('RD_NODE_DEFAULT_CONTAINER_NAME')
    data["follow"] = os.environ.get('RD_CONFIG_FOLLOW')

    common.connect()

    try:
        v1 = client.CoreV1Api()

        if data["follow"] == 'true':

            if data["container"]:
                w = watch.Watch()
                for line in w.stream(v1.read_namespaced_pod_log,
                                     name=data["name"],
                                     namespace=data["namespace"],
                                     follow=False):
                    print(line)
            else:
                w = watch.Watch()
                for line in w.stream(v1.read_namespaced_pod_log, name=data["name"],
                                     container=data["container"],
                                     namespace=data["namespace"],
                                     follow=False):
                    print(line)
        else:
            if data["container"]:
                ret = v1.read_namespaced_pod_log(
                    namespace=data["namespace"],
                    name=data["name"],
                    container=data["container"],
                    _preload_content=False
                )
            else:
                ret = v1.read_namespaced_pod_log(
                    namespace=data["namespace"],
                    name=data["name"],
                    _preload_content=False
                )
            print(ret.read())

    except ApiException:
        log.exception("Exception error creating:")
        sys.exit(1)


if __name__ == '__main__':
    main()
