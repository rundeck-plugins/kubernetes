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
log = logging.getLogger('kubernetes-configmap-create')


def create_config_map(data):

    config_map = client.V1ConfigMap()
    config_map.api_version = data["api_version"]
    config_map.kind = "ConfigMap"

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

    config_map.metadata = metadata

    if "values" in data:
        values = data["values"].split(',')
        values_as_dict = dict(s.split('=') for s in values)
        config_map.data = values_as_dict

    return config_map


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
    data["name"] = os.environ.get('RD_OPTION_NAME')
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

    if os.environ.get('RD_OPTION_VALUES'):
        data["values"] = os.environ.get('RD_OPTION_VALUES')

    api_instance = client.CoreV1Api()

    log.debug("Updating config map from data:")
    log.debug(data)

    config_map = create_config_map(data)

    log.debug("new config map: ")
    log.debug(config_map)

    try:

        configmap_resp = api_instance.patch_namespaced_config_map(
            name=data["name"],
            namespace=data["namespace"],
            body=config_map
        )

        print(common.parseJson(configmap_resp.data))

    except ApiException as e:
        log.error("Exception when calling patch_namespaced_config_map: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
