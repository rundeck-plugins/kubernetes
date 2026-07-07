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
    connection_max_time = 1800 # time in seconds
    connection_max_time_bool = False
    last_line_number = 0
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
            connection_start_time = time.time()
            
            #validate retries
            if retries_count != 0 and not connection_max_time_bool:
                log.warning("An error occurred - retries: {0}".format(retries_count))
            
            if not connection_max_time_bool:
                retries_count = retries_count + 1

                if retries_count > retries:
                    log.error("Number of retries exceeded")
                    completed = True

            if show_log and not completed:
                log.debug("Searching for pod associated with job")
                
                start_time = time.time()
                timeout = 300 #Revisar si este tiempo es suficiente para pods que no logran ser creados
                while True:
                    core_v1 = client.CoreV1Api()
                    try:
                        #get available pod
                        pod_list = core_v1.list_namespaced_pod(
                            namespace,
                            label_selector="job-name==" + name
                        )
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
                            if not connection_max_time_bool:
                                log.info("waiting for log")
                            time.sleep(15)
                            if timeout and time.time() - start_time > timeout:  # pragma: no cover
                                raise TimeoutError

                if not connection_max_time_bool:
                    log.info("Fetching logs from pod: {0}".format(pod_name))
                
                if retries_count == 1 and not connection_max_time_bool:
                    log.info("========================== job log start ==========================")

                connection_max_time_bool = False
                current_line_number = 0
                w = watch.Watch()
                for line in w.stream(core_v1.read_namespaced_pod_log,
                                        name=pod_name,
                                        namespace=namespace):

                    if current_line_number > last_line_number or last_line_number == 0:
                        log.info(line.encode('ascii', 'ignore'))
                        last_line_number = current_line_number
                    
                    current_line_number += 1

                    connection_elapsed_time = time.time() - connection_start_time
                    if connection_elapsed_time >= connection_max_time:
                        connection_max_time_bool = True
                        break 

            if not connection_max_time_bool:
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
