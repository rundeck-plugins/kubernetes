#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client
from kubernetes.client.rest import ApiException

common.log_info_to_stdout()
log = logging.getLogger('kubernetes-read-logs')


def main():
    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = common.get_code_node_parameter_dictionary()
    follow = os.environ.get('RD_CONFIG_FOLLOW') == 'true'

    if not data["name"]:
        log.error("Pod name is not defined. Set RD_CONFIG_NAME or RD_NODE_DEFAULT_NAME.")
        sys.exit(1)

    tail_lines_raw = os.environ.get('RD_CONFIG_NUMBER_OF_LINES')
    tail_lines = None
    if tail_lines_raw:
        try:
            tail_lines = int(tail_lines_raw)
        except ValueError:
            log.error("RD_CONFIG_NUMBER_OF_LINES must be a number, got: %s", tail_lines_raw)
            sys.exit(1)

    common.connect()

    try:
        v1 = client.CoreV1Api()

        kwargs = dict(
            namespace=data["namespace"],
            name=data["name"],
        )
        if tail_lines is not None:
            kwargs['tail_lines'] = tail_lines
        if data["container_name"]:
            kwargs['container'] = data["container_name"]

        if follow:
            from kubernetes import watch
            w = watch.Watch()
            for line in w.stream(v1.read_namespaced_pod_log, follow=True, **kwargs):
                print(line)
        else:
            ret = v1.read_namespaced_pod_log(_preload_content=False, **kwargs)
            # errors='replace' so non-UTF-8 container output still reaches the
            # operator; a UnicodeDecodeError here is not an ApiException and
            # would escape as an unhandled traceback with no logs shown.
            print(ret.read().decode('utf-8', errors='replace'))

    except ApiException:
        log.exception("Exception reading pod logs:")
        sys.exit(1)


if __name__ == '__main__':
    main()
