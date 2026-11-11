#!/usr/bin/env python -u
import logging
import sys
import os
import yaml
import common

from kubernetes import client, dynamic
from kubernetes.dynamic.exceptions import DynamicApiError, ResourceNotFoundError


common.log_info_to_stdout()
log = logging.getLogger('kubernetes-model-source')

# The API version each type is created with.
API_VERSIONS = {
    "Pod": "v1",
    "Deployment": "apps/v1",
    "StatefulSet": "apps/v1",
    "ConfigMap": "v1",
    "Service": "v1",
    "Ingress": "networking.k8s.io/v1",
    "Job": "batch/v1",
    "StorageClass": "storage.k8s.io/v1",
    "PersistentVolume": "v1",
    "PersistentVolumeClaim": "v1",
    "Secret": "v1",
}


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}

    data["type"] = os.environ.get('RD_CONFIG_TYPE')
    data["yaml"] = os.environ.get('RD_CONFIG_YAML')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    if data["type"] not in API_VERSIONS:
        log.error("Unsupported type: %s", data["type"])
        sys.exit(1)

    common.connect()

    try:
        dep = yaml.safe_load(data["yaml"])

        # The dynamic client sends the YAML as it is and leaves validating it
        # to the API server. From kubernetes 37 on, the typed create_* methods
        # validate the body in the client and reject YAML that the API server
        # accepts, such as "cpu: 1".
        dyn = dynamic.DynamicClient(client.ApiClient())
        resource = dyn.resources.get(api_version=API_VERSIONS[data["type"]],
                                     kind=data["type"])
        namespace = data["namespace"] if resource.namespaced else None
        resp = resource.create(body=dep, namespace=namespace)

        # ConfigMap, Secret and StorageClass have no status
        if resp.status is None:
            print(common.parseJson(resp.metadata))
        else:
            print(common.parseJson(resp.status))

    except DynamicApiError as e:
        log.error("Error creating %s: %s", data["type"], e.summary())
        sys.exit(1)
    except (yaml.YAMLError, ResourceNotFoundError, ValueError) as e:
        log.error("Error creating %s: %s", data["type"], e)
        sys.exit(1)


if __name__ == '__main__':
    main()
