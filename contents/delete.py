#!/usr/bin/env python -u
import logging
import sys
import os
import common

from kubernetes import client
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["type"] = os.environ.get('RD_CONFIG_TYPE')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    common.connect()

    try:
        if data["type"] == "Deployment":
            k8s_beta = client.ExtensionsV1beta1Api()
            resp = k8s_beta.delete_namespaced_deployment(
                 name=data["name"],
                 namespace=data["namespace"],
                 body=client.V1DeleteOptions(
                     propagation_policy='Foreground',
                     grace_period_seconds=5),
                 pretty="true")

        if data["type"] == "Service":
            api_instance = client.CoreV1Api()
            resp = api_instance.delete_namespaced_service(
                namespace=data["namespace"],
                name=data["name"],
                body=client.V1DeleteOptions(
                    propagation_policy='Foreground',
                    grace_period_seconds=5),
                pretty="true")

        if data["type"] == "Ingress":
            k8s_beta = client.ExtensionsV1beta1Api()
            body = client.V1DeleteOptions()
            resp = k8s_beta.delete_namespaced_ingress(
                name=data["name"],
                namespace=data["namespace"],
                body=body,
                pretty="true")

        if data["type"] == "Job":
            api_instance = client.BatchV1Api()

            resp = api_instance.delete_namespaced_job(
                name=data["name"],
                namespace=data["namespace"],
                body=client.V1DeleteOptions(api_version='v1',kind="DeleteOptions",propagation_policy="Background"),
                pretty="true"
            )

        if data["type"] == "StorageClass":
            api_instance = client.StorageV1Api()

            resp = api_instance.delete_storage_class(
                name=data["name"],
                body=client.V1DeleteOptions(),
                pretty="true")

        if data["type"] == "PersistentVolumeClaim":
            api_instance = client.CoreV1Api()

            resp = api_instance.delete_namespaced_persistent_volume_claim(
                namespace=data["namespace"],
                body=client.V1DeleteOptions(),
                name=data["name"],
                pretty="true")

        if data["type"] == "Secret":
            api_instance = client.CoreV1Api()

            resp = api_instance.delete_namespaced_secret(
                 namespace=data["namespace"],
                 name=data["name"],
                 body=client.V1DeleteOptions(),
                 pretty="true")

        if data["type"] == "PersistentVolume":
            api_instance = client.CoreV1Api()

            resp = api_instance.delete_persistent_volume(
                namespace=data["namespace"],
                name=data["name"],
                body=client.V1DeleteOptions(),
                pretty="true")

        print(common.parseJson(resp))

    except ApiException as e:
        log.error("Exception error creating: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
