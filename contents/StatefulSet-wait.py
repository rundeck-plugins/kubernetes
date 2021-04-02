#!/usr/bin/env python -u
import logging
import sys
import os
import common
import time


from kubernetes import client
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')


def wait():

    data = {}

    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    retries = int(os.environ.get('RD_CONFIG_RETRIES'))
    sleep = int(os.environ.get('RD_CONFIG_SLEEP'))

    try:
        AppsV1Api = client.AppsV1Api()

        api_response = AppsV1Api.read_namespaced_stateful_set(
            data["name"],
            data["namespace"],
            pretty="True")

        print(common.parseJson(api_response.status))

        current_replicas = api_response.status.current_replicas
        replicas = api_response.spec.replicas
        ready_replicas = api_response.status.ready_replicas

        if ready_replicas is None:
            ready_replicas = 0
        else:
            ready_replicas = int(ready_replicas)

        if replicas is None:
            replicas = 0
        else:
            replicas = int(replicas)

        retries_count = 0

        if (replicas == ready_replicas):
            log.info("Deployment is ready")
            sys.exit(0)

        while ( ready_replicas < replicas ):
            log.info("waiting for StatefulSet")
            time.sleep(float(sleep))
            retries_count = retries_count+1

            if retries_count > retries:
                log.error("number of retries exceeded")
                sys.exit(1)

            api_response = AppsV1Api.read_namespaced_stateful_set(
                data["name"],
                data["namespace"],
                pretty="True")

            replicas = api_response.spec.replicas
            ready_replicas = api_response.status.ready_replicas

            if ready_replicas is None:
                ready_replicas = 0
            else:
                ready_replicas = int(ready_replicas)

            if replicas is None:
                replicas = 0
            else:
                replicas = int(replicas)

            print(common.parseJson(api_response.status))

        log.info("current_replicas" + str(replicas))

    except ApiException as e:
        log.error("Exception deleting StatefulSet: %s\n" % e)
        sys.exit(1)


def main():
    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    common.connect()
    wait()


if __name__ == '__main__':
    main()
