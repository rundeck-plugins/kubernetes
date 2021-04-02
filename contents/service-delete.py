#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-service-delete')


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}

    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    common.connect()

    api_instance = client.CoreV1Api()

    try:

        api_response = api_instance.delete_namespaced_service(
            name=data["name"],
            body=client.V1DeleteOptions(propagation_policy='Foreground',
                                      grace_period_seconds=5),
            namespace=data["namespace"],
            pretty="true"
        )
        print(common.parseJson(api_response))

    except ApiException:
        log.exception("Exception when calling delete_namespaced_service:")
        sys.exit(1)


if __name__ == '__main__':
    main()
