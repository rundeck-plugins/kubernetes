#!/usr/bin/env python -u
import logging
import sys
import common
import time

from kubernetes import client
from kubernetes.client.rest import ApiException
from os import environ

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s: %(name)s: %(message)s"
)
log = logging.getLogger("kubernetes-wait-job")


def wait():
    try:
        name = environ.get("RD_CONFIG_NAME")
        namespace = environ.get("RD_CONFIG_NAMESPACE")
        retries = int(environ.get("RD_CONFIG_RETRIES"))
        sleep = float(environ.get("RD_CONFIG_SLEEP"))
        show_log = environ.get("RD_CONFIG_SHOW_LOG") == "true"

        batch_v1 = client.BatchV1Api()
        core_v1 = client.CoreV1Api()

        # Poll for completion if retries
        retries_count = 0
        completed = False
        while True:
            api_response = batch_v1.read_namespaced_job_status(
                name,
                namespace,
                pretty="True"
            )
            log.debug(api_response)

            retries_count = retries_count + 1
            if retries_count > retries:
                log.error("Number of retries exceeded")
                completed = True

            if api_response.status.conditions:
                for condition in api_response.status.conditions:
                    if condition['type'] == "Failed":
                        completed = True

            if api_response.status.completion_time:
                completed = True

            if completed:
                break

            log.info("Wating for job completion")
            time.sleep(sleep)

        if show_log:
            log.debug("Searching for pod associated with job")
            pod_list = core_v1.list_namespaced_pod(
                namespace,
                label_selector="job-name==" + name
            )
            first_item = pod_list.items[0]
            pod_name = first_item.metadata.name
            log.debug("Fetching logs from pod: {0}".format(pod_name))
            pod_log = core_v1.read_namespaced_pod_log(pod_name, namespace)

            log.info("========================== job log start ==========================")
            log.info(pod_log)
            log.info("=========================== job log end ===========================")

        if api_response.status.succeeded:
            log.info("Job succeeded")
            sys.exit(0)
        else:
            log.info("Job failed")
            sys.exit(1)

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
