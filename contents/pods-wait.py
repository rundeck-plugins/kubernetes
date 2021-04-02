#!/usr/bin/env python -u
import logging
import sys
import common
import time
import os

from kubernetes import client
from kubernetes.client.rest import ApiException
from os import environ

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')

log = logging.getLogger("kubernetes-wait-pod")

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)


def wait():
    try:
        name = environ.get('RD_CONFIG_NAME', environ.get('RD_NODE_DEFAULT_NAME'))
        namespace = environ.get('RD_CONFIG_NAMESPACE', environ.get('RD_NODE_DEFAULT_NAMESPACE', 'default'))
        retries = int(environ.get("RD_CONFIG_RETRIES"))
        sleep = float(environ.get("RD_CONFIG_SLEEP"))
        show_log = environ.get("RD_CONFIG_SHOW_LOG") == "true"

        core_v1 = client.CoreV1Api()

        print("Checking job status ...")
        api_response = core_v1.read_namespaced_pod_status(
            name=name,
            namespace=namespace,
            pretty="True"
        )
        log.debug(api_response.status)

        status = False

        if api_response.status.container_statuses:
           status = api_response.status.container_statuses[0].ready

        # Poll for completion if retries
        retries_count = 0
        while status == False:
            retries_count = retries_count + 1
            if retries_count > retries:
                log.error("Number of retries exceeded")
                sys.exit(1)

            print("Wating for pod completion ... ")
            time.sleep(sleep)
            api_response = core_v1.read_namespaced_pod_status(
                name=name,
                namespace=namespace,
                pretty="True"
            )

            if api_response.status.container_statuses:
                status = api_response.status.container_statuses[0].ready

            log.debug(api_response.status.container_statuses)

        if show_log:
            for i in range(len(api_response.status.container_statuses)):
                log.info("Fetching logs from pod: {0}    -- container {1} ".format(name,api_response.status.container_statuses[i].name))
                pod_log = core_v1.read_namespaced_pod_log(
                    name=name,
                    namespace=namespace,
                    container=api_response.status.container_statuses[i].name
                )

                print("========================== job log start ==========================")
                print(pod_log)
                print("=========================== job log end ===========================")

        if status:
            print("Pod ready")
            sys.exit(0)

    except ApiException as e:
        log.error("Exception waiting for job: %s\n" % e)
        sys.exit(1)


def main():
    if environ.get("RD_CONFIG_DEBUG") == "true":
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    common.connect()
    wait()


if __name__ == "__main__":
    main()
