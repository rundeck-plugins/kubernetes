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


    data = {}

    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    common.connect()

    try:
        extensions_v1beta1 = client.ExtensionsV1beta1Api()

        api_response = extensions_v1beta1.read_namespaced_deployment(
            data["name"],
            data["namespace"])

        print(common.parseJson(api_response.status))

        replicas = api_response.status.replicas
        r_replicas = api_response.status.ready_replicas
        u_replicas = api_response.status.unavailable_replicas

        if(u_replicas is not None):
            log.error(
                "unavailable replicas on the deployment: %s\n" % u_replicas
            )
            sys.exit(1)

        if (replicas != r_replicas):
            log.error(
                "ready replicas doesn't match with replicas: %s\n" % r_replicas
            )
            sys.exit(1)

    except ApiException as e:
        log.error("Exception deleting deployment: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
