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


def create_deployment_object(data):
    # Configure Pod template container

    ports = []

    if "ports" in data:
        for port in data["ports"].split(','):
            portDefinition = client.V1ContainerPort(
                container_port=int(port)
            )
            ports.append(portDefinition)

    envs = []

    if "environments" in data:
        envs_array = data["environments"].splitlines()
        tmp_envs = dict(s.split('=') for s in envs_array)

        for key in tmp_envs:
            envs.append(client.V1EnvVar(
                name=key,
                value=tmp_envs[key])
            )

    if "environments_secrets" in data:
        envs_array = data["environments_secrets"].splitlines()
        tmp_envs = dict(s.split('=') for s in envs_array)

        for key in tmp_envs:

            if(":" in tmp_envs[key]):
                # passing secret env
                value = tmp_envs[key]
                secrets = value.split(':')
                secret_key = secrets[1]
                secret_name = secrets[0]

                envs.append(client.V1EnvVar(
                    name=key,
                    value="",
                    value_from=client.V1EnvVarSource(
                        secret_key_ref=client.V1SecretKeySelector(
                            key=secret_key,
                            name=secret_name)
                    )
                )
                )

    container = client.V1Container(
        name=data["container_name"],
        image=data["image"],
        ports=ports,
        env=envs
    )

    if "liveness_probe" in data:
        container.liveness_probe = common.load_liveness_readiness_probe(
            data["liveness_probe"]
        )

    if "readiness_probe" in data:
        container.readiness_probe = common.load_liveness_readiness_probe(
            data["readiness_probe"]
        )

    if "container_command" in data:
        container.command = data["container_command"].strip().split(' ')

    if "container_args" in data:
        args_array = data["container_args"].splitlines()
        container.args = args_array

    if "resources_requests" in data:
        resources_array = data["resources_requests"].split(",")
        tmp_resources = dict(s.split('=', 1) for s in resources_array)
        container.resources = client.V1ResourceRequirements(
            requests=tmp_resources
        )

    labels = None
    if "labels" in data:
        labels_array = data["labels"].split(',')
        labels = dict(s.split('=') for s in labels_array)

    # Create and configure a spec section
    template = client.V1PodTemplateSpec(
        spec=client.V1PodSpec(containers=[container])
    )
    if labels:
        template.metadata = client.V1ObjectMeta(labels=labels)

    # Create the specification of deployment
    spec = client.V1DeploymentSpec(
        replicas=int(data["replicas"]),
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


def update_deployment(api_instance, deployment, data):
    # Update the deployment
    api_response = api_instance.patch_namespaced_deployment(
        name=data["name"],
        namespace=data["namespace"],
        body=deployment)

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
    if os.environ.get('RD_CONFIG_PORTS'):
        data["ports"] = os.environ.get('RD_CONFIG_PORTS')

    data["replicas"] = os.environ.get('RD_CONFIG_REPLICAS')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    if os.environ.get('RD_CONFIG_LABELS'):
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

    if os.environ.get('RD_CONFIG_CONTAINER_COMMAND'):
        cc = os.environ.get('RD_CONFIG_CONTAINER_COMMAND')
        data["container_command"] = cc

    if os.environ.get('RD_CONFIG_CONTAINER_ARGS'):
        data["container_args"] = os.environ.get('RD_CONFIG_CONTAINER_ARGS')

    if os.environ.get('RD_CONFIG_RESOURCES_REQUESTS'):
        rr = os.environ.get('RD_CONFIG_RESOURCES_REQUESTS')
        data["resources_requests"] = rr

    log.debug("Updating Deployment data:")
    log.debug(data)

    common.connect()

    try:
        apiV1 = client.AppsV1Api()
        deployment = create_deployment_object(data)

        log.debug("deployment object: ")
        log.debug(deployment)

        update_deployment(apiV1, deployment, data)
    except ApiException:
        log.exception("Exception updating deployment:")
        sys.exit(1)


if __name__ == '__main__':
    main()
