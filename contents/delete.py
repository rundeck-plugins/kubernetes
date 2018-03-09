#!/usr/bin/env python -u
import argparse
import logging
import sys
import os

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
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["type"] = os.environ.get('RD_CONFIG_TYPE')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    connect()

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

            print("Deployment deleted. status='%s'" % str(resp.status))

        if data["type"] == "Service":
            api_instance = client.CoreV1Api()
            resp = api_instance.delete_namespaced_service(
                namespace=data["namespace"],
                name=data["name"],
                pretty="true")
            print("Service deleted. status='%s'" % str(resp.status))

        if data["type"] == "Ingress":
            k8s_beta = client.ExtensionsV1beta1Api()
            body = client.V1DeleteOptions()
            resp = k8s_beta.delete_namespaced_ingress(
                name=data["name"],
                namespace=data["namespace"],
                body=body,
                pretty="true")
            print("Ingress deleted. status='%s'" % str(resp.status))

        if data["type"] == "Job":
            api_instance = client.BatchV1Api()
            resp = api_instance.delete_namespaced_job(
                namespace=data["namespace"],
                name=data["name"],
                pretty="true")
            print("Job deleted. status='%s'" % str(resp.status))

        if data["type"] == "StorageClass":
            api_instance = client.StorageV1Api()

            resp = api_instance.delete_storage_class(
                name=data["name"],
                body=client.V1DeleteOptions(),
                pretty="true")
            print("Storage Class deleted. status='%s'" % str(resp))

        if data["type"] == "PersistentVolumeClaim":
            api_instance = client.CoreV1Api()

            resp = api_instance.delete_namespaced_persistent_volume_claim(
                namespace=data["namespace"],
                body=client.V1DeleteOptions(),
                name=data["name"],
                pretty="true")
            print("PVC  deleted. status='%s'" % str(resp.status))

        if data["type"] == "Secret":
            api_instance = client.CoreV1Api()

            resp = api_instance.delete_namespaced_secret(
                 namespace=data["namespace"],
                 name=data["name"],
                 body=client.V1DeleteOptions(),
                 pretty="true")
            print("Secret  deleted. status='%s'" % str(resp.status))

        if data["type"] == "PersistentVolume":
            api_instance = client.CoreV1Api()

            resp = api_instance.delete_persistent_volume(
                namespace=data["namespace"],
                name=data["name"],
                body=client.V1DeleteOptions(),
                pretty="true")
            print("PV deleted. status='%s'" % str(resp.status))

    except ApiException as e:
        log.error("Exception error creating: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
