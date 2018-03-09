#!/usr/bin/env python -u
import argparse
import logging
import sys
import os
import yaml

from kubernetes import client, config
from kubernetes.client import Configuration
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')

parser = argparse.ArgumentParser(
    description='Execute a command string in the container.')

args = parser.parse_args()


def connect():
    config_file = None
    if os.environ.get('RD_CONFIG_CONFIG_FILE'):
        config_file = os.environ.get('RD_CONFIG_CONFIG_FILE')

    url = None
    if os.environ.get('RD_CONFIG_URL'):
        url = os.environ.get('RD_CONFIG_URL')

    verify_ssl = None
    if os.environ.get('RD_CONFIG_VERIFY_SSL'):
        verify_ssl = os.environ.get('RD_CONFIG_VERIFY_SSL')

    ssl_ca_cert = None
    if os.environ.get('RD_CONFIG_SSL_CA_CERT'):
        ssl_ca_cert = os.environ.get('RD_CONFIG_SSL_CA_CERT')

    token = None
    if os.environ.get('RD_CONFIG_TOKEN'):
        token = os.environ.get('RD_CONFIG_TOKEN')

    log.debug("config file")
    log.debug(config_file)
    log.debug("-------------------")

    if config_file:
        log.debug("getting settings from file %s" % config_file)

        config.load_kube_config(config_file=config_file)
    else:

        if url:
            log.debug("getting settings from pluing configuration")

            configuration = Configuration()
            configuration.host = url

            if verify_ssl == 'true':
                configuration.verify_ssl = args.verify_ssl

            if ssl_ca_cert:
                configuration.ssl_ca_cert = args.ssl_ca_cert

            configuration.api_key['authorization'] = token
            configuration.api_key_prefix['authorization'] = 'Bearer'

            client.Configuration.set_default(configuration)
        else:
            log.debug("getting from default config file")
            config.load_kube_config()


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}

    data["type"] = os.environ.get('RD_CONFIG_TYPE')
    data["yaml"] = os.environ.get('RD_CONFIG_YAML')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    connect()

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
