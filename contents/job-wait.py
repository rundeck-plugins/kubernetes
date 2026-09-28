#!/usr/bin/env python -u
import logging
import re
import sys
import common
import time

from datetime import datetime
from kubernetes import client
from kubernetes.client.rest import ApiException


from os import environ

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s: %(name)s: %(message)s"
)
log = logging.getLogger("kubernetes-wait-job")

# With timestamps=True the kubelet starts each log line with an RFC 3339
# timestamp that has up to nine fractional digits, then a space.
LOG_TIMESTAMP = re.compile(
    r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)$")


def parse_log_timestamp(stamp):
    """Return a sortable (datetime, nanoseconds) pair for a kubelet log
    timestamp, or None if stamp is not one.

    Comparing the strings is not enough because the kubelet trims trailing
    zeros from the fraction, and datetime.fromisoformat() on Python 3.10
    accepts neither nanoseconds nor a trailing Z.
    """
    match = LOG_TIMESTAMP.match(stamp)
    if not match:
        return None
    seconds, fraction, zone = match.groups()
    offset = "+00:00" if zone == "Z" else zone
    return (datetime.fromisoformat(seconds + offset),
            int((fraction or "").ljust(9, "0")))


def wait():
    try:
        name = environ.get("RD_CONFIG_NAME")
        namespace = environ.get("RD_CONFIG_NAMESPACE")
        retries = int(environ.get("RD_CONFIG_RETRIES"))
        sleep = float(environ.get("RD_CONFIG_SLEEP"))
        show_log = environ.get("RD_CONFIG_SHOW_LOG") == "true"

        # Poll for completion if retries
        retries_count = 0
        completed = False

        # Newest log timestamp printed, per pod. The loop streams the log
        # again every time round, for example when the container has exited
        # but the Job is not marked complete yet, and the stream always
        # starts from the beginning of the log.
        printed_until = {}


        while True:
            common.connect()

            #validate retries
            if retries_count != 0:
                log.warning("An error occurred - retries: {0}".format(retries_count))
            retries_count = retries_count + 1

            if retries_count > retries:
                log.error("Number of retries exceeded")
                completed = True

            if show_log and not completed:
                log.debug("Searching for pod associated with job")
                
                start_time = time.time()
                timeout = 300 #Revisar si este tiempo es suficiente para pods que no logran ser creados
                while True:
                    if timeout and time.time() - start_time > timeout:
                        raise TimeoutError

                    core_v1 = client.CoreV1Api()
                    try:
                        #get available pod
                        pod_list = core_v1.list_namespaced_pod(
                            namespace,
                            label_selector="job-name==" + name
                        )
                        if not pod_list.items:
                            log.warning("No pods found for job yet, waiting for pod creation")
                            time.sleep(5)
                            continue

                        first_item = pod_list.items[0]
                        pod_name = first_item.metadata.name

                        #try get available log
                        core_v1.read_namespaced_pod_log(name=pod_name,
                                                        namespace=namespace)
                        break
                    except ApiException as ex:
                        log.warning("Pod is not ready, status: %d", ex.status)
                        if ex.status == 200:
                            break
                        else:
                            log.info("waiting for log")
                            time.sleep(15)
                
                log.info("Fetching logs from pod: {0}".format(pod_name))
                
                if retries_count == 1:
                    log.info("========================== job log start ==========================")

                seen = printed_until.get(pod_name)
                # Read the stream directly: in kubernetes 36.0.0 to 36.0.2,
                # watch.Watch().stream() passes watch=True to
                # read_namespaced_pod_log, which rejects it.
                response = core_v1.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=namespace,
                    follow=True,
                    timestamps=True,
                    _preload_content=False)
                try:
                    for raw in response:
                        line = raw.decode("utf-8", errors="replace").rstrip("\n")
                        stamp, _, text = line.partition(" ")
                        when = parse_log_timestamp(stamp)
                        if when is None:
                            text = line
                        elif seen is not None and when <= seen:
                            continue  # printed on an earlier pass
                        else:
                            # The runtime stamps stdout and stderr separately,
                            # so a line can be a little older than the one
                            # before.
                            printed_until[pod_name] = max(
                                when, printed_until.get(pod_name, when))
                        log.info(text.encode('ascii', 'ignore'))
                finally:
                    response.close()
                    response.release_conn()

            #check status job
            batch_v1 = client.BatchV1Api()

            api_response = batch_v1.read_namespaced_job(
                name,
                namespace,
                pretty="True"
            )
            log.debug(api_response)

            if api_response.status.conditions:
                for condition in api_response.status.conditions:
                    if condition.type == "Failed":
                        completed = True

            if api_response.status.completion_time:
                completed = True

            if completed:
                if show_log:
                    log.info("=========================== job log end ===========================")
                break

            log.info("Waiting for job completion")
            time.sleep(sleep)


        if api_response.status.succeeded:
            log.info("Job succeeded")
            sys.exit(0)
        else:
            log.info("Job failed")
            sys.exit(1)

    except ApiException:
        log.exception("Exception waiting for job:")
        sys.exit(1)



def main():
    if environ.get("RD_CONFIG_DEBUG") == "true":
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    #common.connect()
    wait()


if __name__ == "__main__":
    main()
