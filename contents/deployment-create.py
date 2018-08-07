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
    # Configureate Pod template container

    ports = []

    for port in data["ports"].split(','):
        portDefinition = client.V1ContainerPort(container_port=int(port))
        ports.append(portDefinition)

    envs = []
    if "environments" in data:
        envs_array = data["environments"].splitlines()

        tmp_envs = dict(s.split('=', 1) for s in envs_array)

        for key in tmp_envs:
            envs.append(client.V1EnvVar(name=key, value=tmp_envs[key]))

    if "environments_secrets" in data:
        envs_array = data["environments_secrets"].splitlines()
        tmp_envs = dict(s.split('=', 1) for s in envs_array)

        for key in tmp_envs:

            if(":" in tmp_envs[key]):
                # passing secret env
                value = tmp_envs[key]
                secrets = value.split(':')
                secrect_key = secrets[1]
                secrect_name = secrets[0]

                envs.append(client.V1EnvVar(
                    name=key,
                    value="",
                    value_from=client.V1EnvVarSource(
                        secret_key_ref=client.V1SecretKeySelector(
                            key=secrect_key,
                            name=secrect_name))
                    )
                )

    container = client.V1Container(
        name=data["container_name"],
        image=data["image"],
        ports=ports,
        env=envs
    )

    if "volume_mounts" in data:
        volume_mounts = []

        vm_array = data["volume_mounts"].split(",")
        tmp_vm = dict(s.split('=', 1) for s in vm_array)

        for key in tmp_vm:
            volume_mounts.append(client.V1VolumeMount(
                name=key,
                mount_path=tmp_vm[key])
            )

        container.volume_mounts = volume_mounts

    if "liveness_probe" in data:
        container.liveness_probe = common.load_liveness_readiness_probe(
            data["liveness_probe"]
        )

    if "readiness_probe" in data:
        container.readiness_probe = common.load_liveness_readiness_probe(
            data["readiness_probe"]
        )

    if "container_command" in data:
        container.command = data["container_command"].split(' ')

    if "container_args" in data:
        args_array = data["container_args"].splitlines()
        container.args = args_array

    if "resources_requests" in data:
        resources_array = data["resources_requests"].split(",")
        tmp_resources = dict(s.split('=', 1) for s in resources_array)
        container.resources = client.V1ResourceRequirements(
            requests=tmp_resources
        )

    labels_array = data["labels"].split(',')
    labels = dict(s.split('=') for s in labels_array)

    template_spec = client.V1PodSpec(
        containers=[container]
    )

    if "volumes" in data:
        volumes_data = yaml.load(data["volumes"])
        volumes = []

        if (isinstance(volumes_data, list)):
            for volume_data in volumes_data:
                volume = common.create_volume(volume_data)

                if volume:
                    volumes.append(volume)
        else:
            volume = common.create_volume(volumes_data)

            if volume:
                volumes.append(volume)

        template_spec.volumes = volumes

    # Create and configurate a spec section
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels),
        spec=template_spec
    )
    # Create the specification of deployment
    spec = client.ExtensionsV1beta1DeploymentSpec(
        replicas=int(data["replicas"]),
        template=template)
    # Instantiate the deployment object
    deployment = client.ExtensionsV1beta1Deployment(
        api_version=data["api_version"],
        kind="Deployment",
        metadata=client.V1ObjectMeta(labels=labels,
                                     namespace=data["namespace"],
                                     name=data["name"]),
        spec=spec)

    return deployment


def create_deployment(api_instance, deployment, data):
    # Create deployement
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

    log.debug("Creating job from data:")
    log.debug(data)

    common.connect()

    extensions_v1beta1 = client.ExtensionsV1beta1Api()

    deployment = create_deployment_object(data)

    log.debug("new deployment: ")
    log.debug(deployment)

    create_deployment(extensions_v1beta1, deployment, data)


if __name__ == '__main__':
    main()
