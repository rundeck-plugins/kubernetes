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
log = logging.getLogger('kubernetes-service-create')

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

def parsePorts(data):
    ports = yaml.load(data)
    portsList = []

    if (isinstance(ports, list)):
        for x in ports:

            if x.has_key("port"):
                port = client.V1ServicePort(port=int(x["port"]))

                if x.has_key("name"):
                    port.name = x["name"]
                else:
                    port.name = str.lower(x["protocol"] + str(x["port"]))
                if x.has_key("node_port"):
                    port.node_port = x["node_port"]
                if x.has_key("protocol"):
                    port.protocol = x["protocol"]
                if x.has_key("targetPort"):
                    port.target_port = int(x["targetPort"])

                portsList.append(port)
    else:
        x = ports
        port = client.V1ServicePort(port=int(x["port"]))

        if x.has_key("node_port"):
            port.node_port = x["node_port"]
        if x.has_key("protocol"):
            port.protocol = x["protocol"]
        if x.has_key("targetPort"):
            port.target_port = int(x["targetPort"])

        portsList.append(port)

    return portsList

def create_service_object(data):


    service = client.V1Service()
    service.api_version = data["api_version"]
    service.kind = "Service"

    metadata = client.V1ObjectMeta(name=data["name"], namespace=data["namespace"])

    if data.has_key("labels"):
        labels_array = data["labels"].split(',')
        labels = dict(s.split('=') for s in labels_array)
        metadata.labels = labels

    if data.has_key("annotations"):
        annotations_array = data["annotations"].split(',')
        annotations = dict(s.split('=') for s in annotations_array)
        metadata.annotations = annotations

    service.metadata = metadata

    spec = client.V1ServiceSpec()

    if data.has_key("ports"):
        spec.ports = parsePorts(data["ports"])

    if data.has_key("selectors"):
        selectors_array = data["selectors"].split(',')
        selectors = dict(s.split('=') for s in selectors_array)
        spec.selector = selectors

    if data.has_key("type"):
        spec.type=data["type"]

    if data.has_key("external_traffic_policy"):
        spec.external_traffic_policy=data["external_traffic_policy"]
    if data.has_key("session_affinity"):
        spec.session_affinity=data["session_affinity"]
    if data.has_key("external_name"):
        spec.external_name=data["external_name"]
    if data.has_key("load_balancer_ip"):
        spec.load_balancer_ip=data["load_balancer_ip"]

    service.spec = spec

    return service

def main():
    # Configs can be set in Configuration class directly or using helper
    # utility. If no argument provided, the config will be loaded from
    # default location.
    connect()
    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}
    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["name"]=os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    # optionals
    if os.environ.get('RD_CONFIG_ANNOTATIONS'):
        data["annotations"]=os.environ.get('RD_CONFIG_ANNOTATIONS')

    if os.environ.get('RD_CONFIG_TYPE'):
        data["type"] = os.environ.get('RD_CONFIG_TYPE')

    if os.environ.get('RD_CONFIG_LABELS'):
        data["labels"] = os.environ.get('RD_CONFIG_LABELS')

    if os.environ.get('RD_CONFIG_SELECTORS'):
        data["selectors"] = os.environ.get('RD_CONFIG_SELECTORS')

    if os.environ.get('RD_CONFIG_PORTS'):
        data["ports"] = os.environ.get('RD_CONFIG_PORTS')

    if os.environ.get('RD_CONFIG_EXTERNAL_TRAFFIC_POLICY'):
        data["external_traffic_policy"] = os.environ.get('RD_CONFIG_EXTERNAL_TRAFFIC_POLICY')

    if os.environ.get('RD_CONFIG_SESSION_AFFINITY'):
        data["session_affinity"] = os.environ.get('RD_CONFIG_SESSION_AFFINITY')

    if os.environ.get('RD_CONFIG_EXTERNAL_NAME'):
        data["external_name"] = os.environ.get('RD_CONFIG_EXTERNAL_NAME')

    if os.environ.get('RD_CONFIG_LOAD_BALANCER_IP'):
        data["load_balancer_ip"] = os.environ.get('RD_CONFIG_LOAD_BALANCER_IP')

    api_instance = client.CoreV1Api()

    log.debug("Updating service from data:")
    log.debug(data)

    service=create_service_object(data)

    log.debug("new service: ")
    log.debug(service)

    try:

        resp = api_instance.patch_namespaced_service(name=data["name"],namespace=data["namespace"], body=service)
        print("Deployment created. status='%s'" % str(resp.status))

    except ApiException as e:
        log.error("Exception when calling CoreV1Api->create_namespaced_service: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
