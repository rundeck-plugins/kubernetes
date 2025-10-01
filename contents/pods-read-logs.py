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

    data = common.get_code_node_parameter_dictionary()
    data["follow"] = os.environ.get('RD_CONFIG_FOLLOW')

    common.connect()

    try:
        v1 = client.CoreV1Api()

        if data["follow"] == 'true':

            if data["container_name"]:
                w = watch.Watch()
                for line in w.stream(v1.read_namespaced_pod_log,
                                     namespace=data["namespace"],
                                     name=data["name"],
                                     tail_lines=os.environ.get('RD_CONFIG_NUMBER_OF_LINES'),
                                     follow=False):
                    try:
                        log.info(line)
                    except:
                        log.info(line.encode('ascii', 'ignore'))
            else:
                w = watch.Watch()
                for line in w.stream(v1.read_namespaced_pod_log,
                                     container=data["container_name"],
                                     namespace=data["namespace"],
                                     name=data["name"],
                                     tail_lines=os.environ.get('RD_CONFIG_NUMBER_OF_LINES'),
                                     follow=False):
                    try:
                        log.info(line)
                    except:
                        log.info(line.encode('ascii', 'ignore'))
        else:
            if data["container_name"]:
                ret = v1.read_namespaced_pod_log(
                    container=data["container_name"],
                    namespace=data["namespace"],
                    name=data["name"],
                    tail_lines=os.environ.get('RD_CONFIG_NUMBER_OF_LINES'),
                    _preload_content=False
                )
            else:
                ret = v1.read_namespaced_pod_log(
                    namespace=data["namespace"],
                    name=data["name"],
                    tail_lines=os.environ.get('RD_CONFIG_NUMBER_OF_LINES'),
                    _preload_content=False
                )
            print(ret.read())

    except ApiException:
        log.exception("Exception error creating:")
        sys.exit(1)


if __name__ == '__main__':
    main()
