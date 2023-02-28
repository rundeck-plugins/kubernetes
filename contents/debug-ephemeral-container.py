#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client
from kubernetes.client.rest import ApiException
from kubernetes import watch

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format='%(message)s')
log = logging.getLogger('kubernetes-model-source')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)

def main():

    common.connect()

    container_name = os.environ.get("RD_CONFIG_CONTAINER_NAME")
    container_image = os.environ.get("RD_CONFIG_CONTAINER_IMAGE")

    if os.environ.get("RD_CONFIG_TARGET_CONTAINER"):
        target_container = os.environ.get("RD_CONFIG_TARGET_CONTAINER")

    try:
        v1 = client.CoreV1Api()

        [name, namespace, container] = common.get_core_node_parameter_list()

        if not container:
            core_v1 = client.CoreV1Api()
            response = core_v1.read_namespaced_pod_status(
                name=name,
                namespace=namespace,
                pretty="True"
            )
            container = response.spec.containers[0].name

        common.log_pod_parameters(log, {'name': name, 'namespace': namespace, 'container_name': container})
        common.verify_pod_exists(name, namespace)

        # add a debug container to it
        body = {
            "spec": {
                "ephemeralContainers": [
                    {
                        "name": container_name,
                        "image": container_image,
                        "targetContainerName": target_container,
                        "stdin": True,
                        "tty": True,
#                         "volumeMounts": [{
#                             "mountPath": "/var/run/secrets/kubernetes.io/serviceaccount",
#                             "name": "kube-api-access-qnhvv",
#                             "readOnly": true
#                         }]
                    }
                ]
            }
        }

        response = v1.patch_namespaced_pod_ephemeralcontainers(
            name,
            namespace,
            body,
            _preload_content=False)

        print("Ephemeral container " + container_name + " successfully added to pod " + name)

    except ApiException:
        log.exception("Exception error creating:")
        sys.exit(1)

if __name__ == '__main__':
    main()