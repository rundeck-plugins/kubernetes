#!/usr/bin/env python -u
import logging
import sys
import os
import common
import yaml

from kubernetes import client
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')


def create_job_object(data):
    meta = client.V1ObjectMeta(name=data["name"], namespace=data["namespace"])

    labels = None
    if "labels" in data:
        labels_array = data["labels"].split(',')
        labels = dict(s.split('=') for s in labels_array)
        meta.labels = labels

    annotations = None
    if "annotations" in data:
        annotations_array = data["annotations"].split(',')
        annotations = dict(s.split('=') for s in annotations_array)
        meta.annotations = annotations

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

            if (":" in tmp_envs[key]):
                # passing secret env
                value = tmp_envs[key]
                secrets = value.split(':')
                secrect_key = secrets[1]
                secrect_name = secrets[0]

                envs.append(
                    client.V1EnvVar(
                        name=key,
                        value="",
                        value_from=client.V1EnvVarSource(
                            secret_key_ref=client.V1SecretKeySelector(
                                key=secrect_key,
                                name=secrect_name
                            )
                        )
                    )
                )

    container = client.V1Container(name=data["container_name"],
                                   image=data["container_image"],
                                   image_pull_policy=data["image_pull_policy"]
                                   )

    if "container_command" in data:
        container.command = data["container_command"].split(' ')

    if "container_args" in data:
        args_array = data["container_args"].splitlines()
        container.args = args_array

    if "resources_requests" in data:
        resources_array = data["resources_requests"].split(",")
        tmp = dict(s.split('=', 1) for s in resources_array)
        container.resources = client.V1ResourceRequirements(
            requests=tmp
        )

    if "volume_mounts" in data:
        volumes_array = data["volume_mounts"].split(",")
        tmp = dict(s.split('=', 1) for s in volumes_array)

        mounts = []
        for key in tmp:
            mounts.append(client.V1VolumeMount(
                name=key,
                mount_path=tmp[key])
            )

        container.volume_mounts = mounts

    container.env = envs

    template_spec = client.V1PodSpec(
        containers=[
            container
        ],
        restart_policy=data["job_restart_policy"])

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

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(
                    name=data["name"],
                    labels=labels,
                    annotations=annotations,
                ),
        spec=template_spec
    )

    spec = client.V1JobSpec(template=template)

    if "completions" in data:
        spec.completions = int(data["completions"])
    if "selectors" in data:
        selectors_array = data["selectors"].split(',')
        selectors = dict(s.split('=') for s in selectors_array)
        spec.selector = selectors
    if "parallelism" in data:
        spec.parallelism = int(data["parallelism"])
    if "active_deadline_seconds" in data:
        spec.active_deadline_seconds = int(data["active_deadline_seconds"])
    if "backoff_limit" in data:
        spec.backoff_limit = int(data["backoff_limit"])        

    job = client.V1Job(
        api_version=data["api_version"],
        kind='Job',
        metadata=meta,
        spec=spec
    )

    return job


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    common.connect()

    data = {}
    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')
    data["container_name"] = os.environ.get('RD_CONFIG_CONTAINER_NAME')
    data["container_image"] = os.environ.get('RD_CONFIG_CONTAINER_IMAGE')

    data["image_pull_policy"] = os.environ.get('RD_CONFIG_IMAGE_PULL_POLICY')

    if os.environ.get('RD_CONFIG_PARALLELISM'):
        data["parallelism"] = os.environ.get('RD_CONFIG_PARALLELISM')

    if os.environ.get('RD_CONFIG_LABELS'):
        data["labels"] = os.environ.get('RD_CONFIG_LABELS')

    if os.environ.get('RD_CONFIG_ANNOTATIONS'):
        data["annotations"] = os.environ.get('RD_CONFIG_ANNOTATIONS')

    if os.environ.get('RD_CONFIG_SELECTORS'):
        data["selectors"] = os.environ.get('RD_CONFIG_SELECTORS')

    if os.environ.get('RD_CONFIG_CONTAINER_COMMAND'):
        cmd = os.environ.get('RD_CONFIG_CONTAINER_COMMAND')
        data["container_command"] = cmd

    if os.environ.get('RD_CONFIG_CONTAINER_ARGS'):
        data["container_args"] = os.environ.get('RD_CONFIG_CONTAINER_ARGS')

    if os.environ.get('RD_CONFIG_RESOURCES_REQUESTS'):
        req = os.environ.get('RD_CONFIG_RESOURCES_REQUESTS')
        data["resources_requests"] = req

    if os.environ.get('RD_CONFIG_VOLUME_MOUNTS'):
        data["volume_mounts"] = os.environ.get('RD_CONFIG_VOLUME_MOUNTS')

    if os.environ.get('RD_CONFIG_VOLUMES'):
        data["volumes"] = os.environ.get('RD_CONFIG_VOLUMES')

    if os.environ.get('RD_CONFIG_JOB_RESTART_POLICY'):
        rpolicy = os.environ.get('RD_CONFIG_JOB_RESTART_POLICY')
        data["job_restart_policy"] = rpolicy

    if os.environ.get('RD_CONFIG_COMPLETIONS'):
        data["completions"] = os.environ.get('RD_CONFIG_COMPLETIONS')

    if os.environ.get('RD_CONFIG_ACTIVE_DEADLINE_SECONDS'):
        active_ds = os.environ.get('RD_CONFIG_ACTIVE_DEADLINE_SECONDS')
        data["active_deadline_seconds"] = active_ds

    if os.environ.get('RD_CONFIG_BACKOFF_LIMIT'):
        backoff_limit = os.environ.get('RD_CONFIG_BACKOFF_LIMIT')
        data["backoff_limit"] = backoff_limit

    if os.environ.get('RD_CONFIG_ENVIRONMENTS'):
        data["environments"] = os.environ.get('RD_CONFIG_ENVIRONMENTS')

    if os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS'):
        esecret = os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS')
        data["environments_secrets"] = esecret

    log.debug("Creating job")
    log.debug(data)

    job = create_job_object(data)

    log.debug("new job: ")
    log.debug(job)

    try:

        k8s_client = client.BatchV1Api()
        api_response = k8s_client.create_namespaced_job(
            body=job,
            namespace=data["namespace"]
        )

        print(common.parseJson(api_response.status))

    except ApiException as e:
        log.error("Exception creating job: %s\n" % e)
        sys.exit(1)


if __name__ == '__main__':
    main()
