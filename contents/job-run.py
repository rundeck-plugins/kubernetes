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
        field_selector = os.environ.get('RD_CONFIG_TOKEN')

    log.debug("config file")
    log.debug(config_file)
    log.debug("-------------------")

    if config_file:
        # Configs can be set in Configuration class directly or using helper utility
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

    connect()

    data={}
    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')



    try:

        k8s_client = client.BatchV1Api()
        job = k8s_client.read_namespaced_job(name=data["name"],namespace=data["namespace"])
        job.metadata.creation_timestamp=None
        job.metadata.uid = None
        job.metadata.resource_version = None
        job.status=None
        job.spec.selector=None
        job.spec.template.metadata = None


        body = client.V1DeleteOptions()  # V1DeleteOptions |
        pretty = 'pretty_example'

        api_response = k8s_client.delete_namespaced_job(name=data["name"], namespace=data["namespace"], body=body,
                                                        pretty=pretty)

        print("Job deleted. status='%s'" % str(api_response.status))

        api_response = k8s_client.create_namespaced_job(body=job, namespace=data["namespace"])
        print("Job created. status='%s'" % str(api_response.status))



    except ApiException as e:
        log.error("Exception creating job: %s\n" % e)
        sys.exit(1)



if __name__ == '__main__':
    main()
