#!/usr/bin/env python -u
import argparse
import logging
import sys
import os
from pprint import pprint
import time

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


def wait():

    data = {}

    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    retries = os.environ.get('RD_CONFIG_RETRIES')
    sleep = os.environ.get('RD_CONFIG_SLEEP')

    try:
        extensions_v1beta1 = client.ExtensionsV1beta1Api()

        api_response = extensions_v1beta1.read_namespaced_deployment(
            data["name"],
            data["namespace"],
            pretty="True")

        pprint(api_response.status)

        unavailable_replicas = api_response.status.unavailable_replicas
        replicas = api_response.status.replicas
        ready_replicas = api_response.status.ready_replicas

        retries_count = 0

        if (replicas == ready_replicas):
            log.info("Deployment is ready")
            sys.exit(0)

        while (unavailable_replicas is not None):
            log.info("wating for deployment")
            time.sleep(float(sleep))
            retries_count = retries_count+1

            if retries_count > retries:
                log.error("number retries exedded")
                sys.exit(1)

            api_response = extensions_v1beta1.read_namespaced_deployment(
                data["name"],
                data["namespace"],
                pretty="True")
            u_replicas = api_response.status.unavailable_replicas

            log.info("unavailable replicas: " + str(u_replicas))

    except ApiException as e:
        log.error("Exception deleting deployment: %s\n" % e)
        sys.exit(1)


def main():
    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    connect()
    wait()


if __name__ == '__main__':
    main()
