#!/usr/bin/env python -u
import logging
import sys
import os
import common
import time


from kubernetes import client
from kubernetes.client.rest import ApiException


common.log_info_to_stdout()
log = logging.getLogger('kubernetes-model-source')


def rollout_complete(deployment):
    """True when the rollout of the current spec has finished: the same test
    as "kubectl rollout status".

    Comparing status.replicas with status.ready_replicas is not enough. Both
    are unset on a Deployment that was just created, and both still describe
    the old pods just after an update, until the controller has seen it.
    """
    status = deployment.status
    generation = deployment.metadata.generation or 0
    if (status.observed_generation or 0) < generation:
        return False

    wanted = deployment.spec.replicas
    if wanted is None:
        wanted = 1
    updated = status.updated_replicas or 0

    return (updated == wanted
            and (status.replicas or 0) == updated
            and (status.available_replicas or 0) == updated)


def wait():

    data = {}

    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    retries = int(os.environ.get('RD_CONFIG_RETRIES'))
    sleep = float(os.environ.get('RD_CONFIG_SLEEP'))

    try:
        appsV1Api = client.AppsV1Api()

        api_response = appsV1Api.read_namespaced_deployment(
            data["name"],
            data["namespace"],
            pretty="True")

        print(common.parseJson(api_response.status))

        retries_count = 0

        while not rollout_complete(api_response):
            retries_count = retries_count+1

            if retries_count > retries:
                log.error("number of retries exceeded")
                sys.exit(1)

            log.info("waiting for deployment")
            time.sleep(sleep)

            api_response = appsV1Api.read_namespaced_deployment(
                data["name"],
                data["namespace"],
                pretty="True")

            log.info("unavailable replicas: " + str(api_response.status.unavailable_replicas))

        log.info("Deployment is ready")

    except ApiException:
        log.exception("Exception waiting for deployment:")
        sys.exit(1)


def main():
    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    common.connect()
    wait()


if __name__ == '__main__':
    main()
