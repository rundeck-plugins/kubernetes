#!/usr/bin/env python -u
import logging
import sys
import time
from os import environ

import common
from kubernetes import client, watch
from kubernetes.client.rest import ApiException

logging.basicConfig(
    stream=sys.stderr, level=logging.INFO, format="%(levelname)s: %(message)s"
)
log = logging.getLogger("kubernetes-wait-job")

# OUTPUT
START_STRING = "========================== job log start =========================="
END_STRING = "=========================== job log end ==========================="
JOB_COMPLETED_STRING = (
    "=========================== JOB COMPLETED ==========================="
)
JOB_SUCCEEDED_STRING = (
    "========================== JOB SUCCEEDED =========================="
)
JOB_FAILED_STRING = "=========================== JOB FAILED ==========================="

# API CONNECTION
common.connect()
batch_api = client.BatchV1Api()
core_api = client.CoreV1Api()

# TIMEOUT CONFIG
job_ready_timeout = int(environ.get("RD_CONFIG_JOB_READY_TIMEOUT"))
pod_ready_timeout = int(environ.get("RD_CONFIG_POD_READY_TIMEOUT"))
pod_execution_timeout = int(environ.get("RD_CONFIG_POD_EXECUTION_TIMEOUT"))
job_execution_timeout = int(environ.get("RD_CONFIG_JOB_EXECUTION_TIMEOUT"))


def wait_for_job(job_name, namespace):
    """Wait until the job is found."""

    start_time = time.time()
    while True:
        if time.time() - start_time > job_ready_timeout:
            raise TimeoutError
        try:
            job = batch_api.read_namespaced_job_status(job_name, namespace, pretty=True)
            return job
        except ApiException as ex:
            log.debug("Job not ready. Status: {}".format(ex.status))
            time.sleep(1)


def is_job_succeeded(job):
    """Return True if the passed job is succeeded."""

    return job.status.completion_time is not None


def is_job_failed(job):
    """Return True is the passed job is failed."""

    if job.status.conditions:
        for condition in job.status.conditions:
            if condition.type == "Failed":
                return True
        return False
    return False


def is_job_completed(job):
    """Return True if the passed job is succeeded or failed."""

    return is_job_succeeded(job) or is_job_failed(job)


def get_latest_pod(job_name, namespace, timeout=10):
    """Return the last pod created by the K8S job resource"""

    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            log.exception("Timeout waiting for latest job execution")
            raise TimeoutError
        pod_list = core_api.list_namespaced_pod(
            namespace, label_selector="job-name==" + job_name
        )
        sorted_list = sorted(
            [{"pod": x, "time": x.status.start_time} for x in pod_list.items],
            key=lambda d: d["time"],
            reverse=True,
        )
        try:
            return sorted_list[0]["pod"]
        except KeyError:
            log.debug("No pod found. Sleep and retry")
            time.sleep(1)
            continue


def is_pod_running(pod):
    """Return True if the pod not succeeded or failed."""

    return pod.status.phase not in ["Succeeded", "Failed"]


def follow_pod(pod, show_log):
    """Follow a pod execution until end.

    Wait until pod logs are available with a timeout handled by
    `pod_ready_timeout` config. Logs availability is used as probe.
    Wait until the pod is succeeded or failed with a Timeout of `pod_execution_timeout`
    If show_log is true, stream pod logs.
    """

    log.info("------ Follow execution pod: {} ------".format(pod.metadata.name))
    start_time = time.time()
    while True:
        if time.time() - start_time > pod_ready_timeout:
            log.exception("Timeout while waiting for pod logs")
            raise TimeoutError
        try:
            core_api.read_namespaced_pod_log(
                name=pod.metadata.name, namespace=pod.metadata.namespace
            )
            break
        except ApiException as ex:
            log.debug("Pod not ready. Status {}".format(ex.status))
            time.sleep(1)

    w = watch.Watch()
    streamed = 0
    start_time = time.time()
    while True:
        if time.time() - start_time > pod_execution_timeout:
            log.exception("Timeout while following pod")
            raise TimeoutError
        if show_log:
            line_n = 0
            for line in w.stream(
                core_api.read_namespaced_pod_log,
                name=pod.metadata.name,
                namespace=pod.metadata.namespace,
            ):
                line_n += 1
                if line_n > streamed:
                    log.info(line)
                    streamed += 1
        pod = core_api.read_namespaced_pod_status(
            pod.metadata.name, pod.metadata.namespace
        )
        if is_pod_running(pod):
            if not show_log:
                log.debug("Pod still running...")
                time.sleep(5)
            continue
        break
    return


def is_job_active(job):
    """Return True is the job is in status ACTIVE"""

    return job.status.active == 1


def wait_for_job_active(job_name, namespace):
    """Wait for job to be active with a timeout defined by `job_ready_timeout`."""

    start_time = time.time()
    while True:
        if time.time() - start_time > job_ready_timeout:
            log.exception("Timeout waiting for job to be active")
            raise TimeoutError
        job = batch_api.read_namespaced_job_status(job_name, namespace, pretty=True)
        if is_job_active(job):
            return job
        log.info("Job not yet active")
        time.sleep(1)


def wait_for_job_completed(job, timeout=20):
    """Wait until the job status is completed.

    Doen't follow the job execution, just wait until the K8S job status
    is correctly updated.
    To be used only when you're reasonably sure that the job is succeeded or
    failed, including any backoff retry.
    """

    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            log.exception("Timeout while waiting for job status complete")
            print(job.status)
            raise TimeoutError
        job = batch_api.read_namespaced_job_status(
            job.metadata.name, job.metadata.namespace, pretty=True
        )
        if is_job_completed(job):
            return job
        log.debug("Job not completed yet")
        time.sleep(2)


def follow_job(job, show_log):
    """Follow a running job execution.

    It is designed to be able to "attach" on a job that is already failed
    at least one time and is in a retry step."""

    backoff = job.spec.backoff_limit
    failed_n = job.status.failed
    if not failed_n:
        failed_n = 0
    streamed = []
    start_time = time.time()
    for i in range(failed_n, backoff + 1):
        if time.time() - start_time > job_execution_timeout:
            log.exception("Timeout while follow job execution")
            raise TimeoutError
        if i > 0:
            log.warning(
                "Execution failed. Wait for job retry {}/{}".format(i + 1, backoff + 1)
            )
        else:
            log.info("Wait for execution {}/{}".format(i + 1, backoff + 1))
        while True:
            if time.time() - start_time > job_execution_timeout:
                log.exception("Timeout while follow job execution")
                raise TimeoutError
            pod = get_latest_pod(
                job.metadata.name, job.metadata.namespace, pod_ready_timeout
            )
            if pod.metadata.name not in streamed:
                follow_pod(pod, show_log)
                streamed.append(pod.metadata.name)
                break
            log.debug("Pod not found, sleep and retry.")
            time.sleep(2)

        pod = core_api.read_namespaced_pod(pod.metadata.name, pod.metadata.namespace)
        if pod.status.phase == "Succeeded":
            break

    return batch_api.read_namespaced_job_status(
        job.metadata.name, job.metadata.namespace
    )


def main():
    if environ.get("RD_CONFIG_DEBUG") == "true":
        log.setLevel(logging.DEBUG)
    log.debug("Log level configured for DEBUG")

    job_name = environ.get("RD_CONFIG_NAME")
    namespace = environ.get("RD_CONFIG_NAMESPACE")
    show_log = environ.get("RD_CONFIG_SHOW_LOG") == "true"

    job_name = "test-fx"
    namespace = "rundeck"
    show_log = False

    log.debug("Retrieving job...")
    job = wait_for_job(job_name, namespace)
    log.info("Job found")

    # if completed, just stream logs if needed and exit
    if is_job_completed(job):
        log.info(JOB_COMPLETED_STRING)
        if show_log:
            log.debug("Try to print last execution logs")
            # a shot timeout here. The job is alredy completed
            latest_pod = get_latest_pod(job_name, namespace, 3)
            log.info(START_STRING)
            follow_pod(latest_pod, show_log)
            log.info(END_STRING)
        if is_job_succeeded(job):
            log.info(JOB_SUCCEEDED_STRING)
            return 0
        log.error(JOB_FAILED_STRING)
        return 1

    # wait until the job is active
    log.debug("Waiting for job to be active")
    job = wait_for_job_active(job_name, namespace)
    log.info("job active")

    if show_log:
        log.info(START_STRING)
    job = follow_job(job, show_log)
    if show_log:
        log.info(END_STRING)

    # We are reasonably sure that the job is completed here
    # just wait for K8S api to update the resource
    job = wait_for_job_completed(job)
    log.info(JOB_COMPLETED_STRING)

    if is_job_succeeded(job):
        log.info(JOB_SUCCEEDED_STRING)
        return 0
    else:
        log.error(JOB_FAILED_STRING)
        return 1


if __name__ == "__main__":
    sys.exit(main())
