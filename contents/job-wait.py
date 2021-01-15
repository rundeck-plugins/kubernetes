#!/usr/bin/env python -u
import logging
import sys
import common
import time

from kubernetes import client
from kubernetes.client.rest import ApiException
from kubernetes import watch


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

        # Poll for completion if retries
        retries_count = 0
        completed = False


        while True:

            common.connect()

            batch_v1 = client.BatchV1Api()
            core_v1 = client.CoreV1Api()

            api_response = batch_v1.read_namespaced_job_status(
                name,
                namespace,
                pretty="True"
            )
            log.debug(api_response)

            #for condition in api_response.status.conditions:
            #    log.info(condition.type)

            retries_count = retries_count + 1
            if retries_count > retries:
                log.error("Number of retries exceeded")
                completed = True

            if api_response.status.conditions:
                for condition in api_response.status.conditions:
                    if condition.type == "Failed":
                        completed = True


            if api_response.status.completion_time:
                completed = True

            if show_log:
                log.debug("Searching for pod associated with job")

                schedule_start_time = time.time()
                schedule_timeout = 600
                while True:
                    try:
                        pod_list = core_v1.list_namespaced_pod(
                            namespace,
                            label_selector="job-name==" + name
                        )
                        first_item = pod_list.items[0]
                        pod_name = first_item.metadata.name
                        break
                    except IndexError as IndexEx:
                        log.warning("Still Waiting for Pod to be Scheduled")
                        time.sleep(60)
                        if schedule_timeout and time.time() - schedule_start_time > schedule_timeout:  # pragma: no cover
                            raise TimeoutError

                log.info("Fetching logs from pod: {0}".format(pod_name))

                # time.sleep(15)
                log.info("========================== job log start ==========================")
                start_time = time.time()
                timeout = 300
                while True:
                    try:
                        core_v1.read_namespaced_pod_log(name=pod_name,
                                                        namespace=namespace)
                        break
                    except ApiException as ex:
                        log.warning("Pod is not ready, status: {}".format(ex.status))
                        if ex.status == 200:
                            break
                        else:
                            log.info("waiting for log")
                            time.sleep(15)
                            if timeout and time.time() - start_time > timeout:  # pragma: no cover
                                raise TimeoutError

                w = watch.Watch()
                for line in w.stream(core_v1.read_namespaced_pod_log,
                                        name=pod_name,
                                        namespace=namespace):
                    print(line)

                log.info("=========================== job log end ===========================")

            if completed:
                break

            log.info("Waiting for job completion")
            show_log = False
            time.sleep(sleep)




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
