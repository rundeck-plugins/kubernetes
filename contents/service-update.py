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
log = logging.getLogger('kubernetes-service-create')


def create_service_object(data):

    service = client.V1Service()
    service.api_version = data["api_version"]
    service.kind = "Service"

    metadata = client.V1ObjectMeta(
        name=data["name"],
        namespace=data["namespace"]
    )

    if "labels" in data:
        labels_array = data["labels"].split(',')
        labels = dict(s.split('=') for s in labels_array)
        metadata.labels = labels

    if "annotations" in data:
        annotations_array = data["annotations"].split(',')
        annotations = dict(s.split('=') for s in annotations_array)
        metadata.annotations = annotations

    service.metadata = metadata

    spec = client.V1ServiceSpec()

    if "ports" in data:
        spec.ports = common.parsePorts(data["ports"])

    if "selectors" in data:
        selectors_array = data["selectors"].split(',')
        selectors = dict(s.split('=') for s in selectors_array)
        spec.selector = selectors

    if "type" in data:
        spec.type = data["type"]

    if "external_traffic_policy" in data:
        spec.external_traffic_policy = data["external_traffic_policy"]
    if "session_affinity" in data:
        spec.session_affinity = data["session_affinity"]
    if "external_name" in data:
        spec.external_name = data["external_name"]
    if "load_balancer_ip" in data:
        spec.load_balancer_ip = data["load_balancer_ip"]

    service.spec = spec

    return service


def main():
    # Configs can be set in Configuration class directly or using helper
    # utility. If no argument provided, the config will be loaded from
    # default location.
    common.connect()

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}
    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    # optionals
    if os.environ.get('RD_CONFIG_ANNOTATIONS'):
        data["annotations"] = os.environ.get('RD_CONFIG_ANNOTATIONS')

    if os.environ.get('RD_CONFIG_TYPE'):
        data["type"] = os.environ.get('RD_CONFIG_TYPE')

    if os.environ.get('RD_CONFIG_LABELS'):
        data["labels"] = os.environ.get('RD_CONFIG_LABELS')

    if os.environ.get('RD_CONFIG_SELECTORS'):
        data["selectors"] = os.environ.get('RD_CONFIG_SELECTORS')

    if os.environ.get('RD_CONFIG_PORTS'):
        data["ports"] = os.environ.get('RD_CONFIG_PORTS')

    if os.environ.get('RD_CONFIG_EXTERNAL_TRAFFIC_POLICY'):
        et_policy = os.environ.get('RD_CONFIG_EXTERNAL_TRAFFIC_POLICY')
        data["external_traffic_policy"] = et_policy

    if os.environ.get('RD_CONFIG_SESSION_AFFINITY'):
        data["session_affinity"] = os.environ.get('RD_CONFIG_SESSION_AFFINITY')

    if os.environ.get('RD_CONFIG_EXTERNAL_NAME'):
        data["external_name"] = os.environ.get('RD_CONFIG_EXTERNAL_NAME')

    if os.environ.get('RD_CONFIG_LOAD_BALANCER_IP'):
        data["load_balancer_ip"] = os.environ.get('RD_CONFIG_LOAD_BALANCER_IP')

    api_instance = client.CoreV1Api()

    log.debug("Updating service from data:")
    log.debug(data)

    service = create_service_object(data)

    log.debug("new service: ")
    log.debug(service)

    try:

        resp = api_instance.patch_namespaced_service(
            name=data["name"],
            namespace=data["namespace"],
            body=service
        )
        print("Deployment created. status='%s'" % str(resp.status))

    except ApiException as e:
        log.error("Exception when calling create_namespaced_service: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
