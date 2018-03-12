#!/usr/bin/env python -u
import logging
import sys
import os
import yaml
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

    data["type"] = os.environ.get('RD_CONFIG_TYPE')
    data["yaml"] = os.environ.get('RD_CONFIG_YAML')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    common.connect()

    try:
        if data["type"] == "Deployment":
            dep = yaml.load(data["yaml"])
            k8s_beta = client.ExtensionsV1beta1Api()
            resp = k8s_beta.create_namespaced_deployment(
                    body=dep,
                    namespace=data["namespace"],
                    pretty="true")

            print("Deployment created. status='%s'" % str(resp.status))

        if data["type"] == "Service":
            api_instance = client.CoreV1Api()
            dep = yaml.load(data["yaml"])
            resp = api_instance.create_namespaced_service(
                    namespace=data["namespace"],
                    body=dep,
                    pretty="true")

            print("Service created. status='%s'" % str(resp.status))

        if data["type"] == "Ingress":
            dep = yaml.load(data["yaml"])
            k8s_beta = client.ExtensionsV1beta1Api()
            resp = k8s_beta.create_namespaced_ingress(
                    body=dep,
                    namespace=data["namespace"],
                    pretty="true")
            print("Ingress created. status='%s'" % str(resp.status))

        if data["type"] == "Job":
            api_instance = client.BatchV1Api()
            dep = yaml.load(data["yaml"])
            resp = api_instance.create_namespaced_job(
                    namespace=data["namespace"],
                    body=dep,
                    pretty="true")
            print("Job created. status='%s'" % str(resp.status))

        if data["type"] == "StorageClass":
            dep = yaml.load(data["yaml"])
            api_instance = client.StorageV1Api()

            resp = api_instance.create_storage_class(body=dep,
                                                     pretty="true")
            print("Storage Class created '%s'" % str(resp))

        if data["type"] == "PersistentVolumeClaim":
            dep = yaml.load(data["yaml"])
            api_instance = client.CoreV1Api()

            resp = api_instance.create_namespaced_persistent_volume_claim(
                    namespace=data["namespace"],
                    body=dep,
                    pretty="true")
            print("PVC created ='%s'" % str(resp.status))

        if data["type"] == "Secret":
            dep = yaml.load(data["yaml"])
            api_instance = client.CoreV1Api()

            resp = api_instance.create_namespaced_secret(
                    namespace=data["namespace"],
                    body=dep,
                    pretty="true")
            print("Secret created '%s'" % str(resp.status))

        if data["type"] == "PersistentVolume":
            dep = yaml.load(data["yaml"])
            api_instance = client.CoreV1Api()

            resp = api_instance.create_persistent_volume(
                    namespace=data["namespace"],
                    body=dep,
                    pretty="true")
            print("PV created '%s'" % str(resp.status))

    except ApiException as e:
        log.error("Exception error creating: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
