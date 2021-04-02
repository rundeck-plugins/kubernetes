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


def delete_deployment(api_instance, data):
    # Delete deployment
    api_response = api_instance.delete_namespaced_deployment(
        name=data["name"],
        namespace=data["namespace"],
        body=client.V1DeleteOptions(
            propagation_policy='Foreground',
            grace_period_seconds=5))

    print(common.parseJson(api_response.status))


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}

    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    common.connect()

    try:
        apps_v1 = client.AppsV1Api()

        delete_deployment(apps_v1, data)
    except ApiException:
        log.exception("Exception deleting deployment:")
        sys.exit(1)


if __name__ == '__main__':
    main()
