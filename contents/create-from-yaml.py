#!/usr/bin/env python -u
import logging
import sys
import os
import yaml
import common

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from openshift.dynamic import DynamicClient

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}

    data["type"] = os.environ.get('RD_CONFIG_TYPE')
    data["yaml"] = os.environ.get('RD_CONFIG_YAML')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    common.connect()

    try:
        if data["type"] == "Deployment":
            dep = yaml.safe_load(data["yaml"])
            api_instance = client.AppsV1Api()
            resp = api_instance.create_namespaced_deployment(
                body=dep,
                namespace=data["namespace"],
                pretty="true")

            print(common.parseJson(resp.status))

        if data["type"] == "ConfigMap":
            api_instance = client.CoreV1Api()
            dep = yaml.safe_load(data["yaml"])
            resp = api_instance.create_namespaced_config_map(
                namespace=data["namespace"],
                body=dep,
                pretty="true")

            print(common.parseJson(resp.metadata))

        if data["type"] == "StatefulSet":
            dep = yaml.safe_load(data["yaml"])
            k8s_beta = client.AppsV1Api()
            resp = k8s_beta.create_namespaced_stateful_set(
                body=dep,
                namespace=data["namespace"],
                pretty="true")

            print(common.parseJson(resp.status))

        if data["type"] == "Service":
            api_instance = client.CoreV1Api()
            dep = yaml.safe_load(data["yaml"])
            resp = api_instance.create_namespaced_service(
                namespace=data["namespace"],
                body=dep,
                pretty="true")

            print(common.parseJson(resp.status))

        if data["type"] == "Ingress":
            dep = yaml.safe_load(data["yaml"])
            k8s_beta = client.ExtensionsV1beta1Api()
            resp = k8s_beta.create_namespaced_ingress(
                body=dep,
                namespace=data["namespace"],
                pretty="true")

            print(common.parseJson(resp.status))

        if data["type"] == "Job":
            api_instance = client.BatchV1Api()
            dep = yaml.safe_load(data["yaml"])
            resp = api_instance.create_namespaced_job(
                namespace=data["namespace"],
                body=dep,
                pretty="true")

            print(common.parseJson(resp.status))

        if data["type"] == "StorageClass":
            dep = yaml.safe_load(data["yaml"])
            api_instance = client.StorageV1Api()

            resp = api_instance.create_storage_class(body=dep,
                                                     pretty="true")

            print(common.parseJson(resp.metadata))

        if data["type"] == "PersistentVolumeClaim":
            dep = yaml.safe_load(data["yaml"])
            api_instance = client.CoreV1Api()

            resp = api_instance.create_namespaced_persistent_volume_claim(
                namespace=data["namespace"],
                body=dep,
                pretty="true")

            print(common.parseJson(resp.status))

        if data["type"] == "Secret":
            dep = yaml.safe_load(data["yaml"])
            api_instance = client.CoreV1Api()

            resp = api_instance.create_namespaced_secret(
                namespace=data["namespace"],
                body=dep,
                pretty="true")

            print(common.parseJson(resp.metadata))

        if data["type"] == "PersistentVolume":
            dep = yaml.safe_load(data["yaml"])
            api_instance = client.CoreV1Api()

            resp = api_instance.create_persistent_volume(
                body=dep,
                pretty="true")

            print(common.parseJson(resp.status))

        if data["type"] == "BuildConfig":
            dep = yaml.safe_load(data["yaml"])

            k8s_client = config.new_client_from_config()
            openshift_client = DynamicClient(k8s_client)
            v1_bc = openshift_client.resources.get(api_version='build.openshift.io/v1', kind='BuildConfig')

            resp = v1_bc.create(body=dep, namespace=data["namespace"])

            print(common.parseJson(resp.metadata))
    except ApiException as e:
        log.error("Exception error creating: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
