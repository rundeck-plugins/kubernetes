#!/usr/bin/env python -u
import logging
import sys
import os
import yaml
import common

from kubernetes import client


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')


def create_deployment_object(data):
    # Configure Pod template container

    template_spec = common.create_pod_template_spec(data=data)

    labels_array = data["labels"].split(',')
    labels = dict(s.split('=') for s in labels_array)

    meta = client.V1ObjectMeta(labels=labels)

    annotations = None
    if "annotations" in data:
        annotations_array = data["annotations"].split(',')
        annotations = dict(s.split('=') for s in annotations_array)
        meta.annotations = annotations

    # Create and configure a spec section
    template = client.V1PodTemplateSpec(
        metadata=meta,
        spec=template_spec
    )
    # Create the specification of deployment
    spec = client.V1DeploymentSpec(
        replicas=int(data["replicas"]),
        selector={"matchLabels": labels},
        template=template)
    # Instantiate the deployment object
    deployment = client.V1Deployment(
        api_version=data["api_version"],
        kind="Deployment",
        metadata=client.V1ObjectMeta(labels=labels,
                                     namespace=data["namespace"],
                                     name=data["name"]),
        spec=spec)

    return deployment


def create_deployment(api_instance, deployment, data):
    # Create deployment
    api_response = api_instance.create_namespaced_deployment(
        body=deployment,
        namespace=data["namespace"])

    print(common.parseJson(api_response.status))


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}

    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["container_name"] = os.environ.get('RD_CONFIG_CONTAINER_NAME')
    data["image"] = os.environ.get('RD_CONFIG_IMAGE')
    data["ports"] = os.environ.get('RD_CONFIG_PORTS')
    data["replicas"] = os.environ.get('RD_CONFIG_REPLICAS')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')
    data["labels"] = os.environ.get('RD_CONFIG_LABELS')

    if os.environ.get('RD_CONFIG_ENVIRONMENTS'):
        data["environments"] = os.environ.get('RD_CONFIG_ENVIRONMENTS')

    if os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS'):
        evs = os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS')
        data["environments_secrets"] = evs

    if os.environ.get('RD_CONFIG_LIVENESS_PROBE'):
        data["liveness_probe"] = os.environ.get('RD_CONFIG_LIVENESS_PROBE')

    if os.environ.get('RD_CONFIG_READINESS_PROBE'):
        data["readiness_probe"] = os.environ.get('RD_CONFIG_READINESS_PROBE')

    if os.environ.get('RD_CONFIG_VOLUME_MOUNTS'):
        data["volume_mounts"] = os.environ.get('RD_CONFIG_VOLUME_MOUNTS')

    if os.environ.get('RD_CONFIG_VOLUMES'):
        data["volumes"] = os.environ.get('RD_CONFIG_VOLUMES')

    if os.environ.get('RD_CONFIG_CONTAINER_COMMAND'):
        cc = os.environ.get('RD_CONFIG_CONTAINER_COMMAND')
        data["container_command"] = cc

    if os.environ.get('RD_CONFIG_CONTAINER_ARGS'):
        data["container_args"] = os.environ.get('RD_CONFIG_CONTAINER_ARGS')

    if os.environ.get('RD_CONFIG_RESOURCES_REQUESTS'):
        rr = os.environ.get('RD_CONFIG_RESOURCES_REQUESTS')
        data["resources_requests"] = rr

    if os.environ.get('RD_CONFIG_RESOURCES_LIMITS'):
        rl = os.environ.get('RD_CONFIG_RESOURCES_LIMITS')
        data["resources_limits"] = rl

    if os.environ.get('RD_CONFIG_ANNOTATIONS'):
        data["annotations"] = os.environ.get('RD_CONFIG_ANNOTATIONS')

    if os.environ.get('RD_CONFIG_IMAGEPULLSECRETS'):
        data["image_pull_secrets"] = os.environ.get('RD_CONFIG_IMAGEPULLSECRETS')

    log.debug("Creating job from data:")
    log.debug(data)

    common.connect()

    apiV1 = client.AppsV1Api()

    deployment = create_deployment_object(data)
    create_deployment(apiV1, deployment, data)


if __name__ == '__main__':
    main()
