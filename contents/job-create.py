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


def create_job_object(data):
    meta = client.V1ObjectMeta(name=data["name"], namespace=data["namespace"])

    if data.has_key("labels"):
        labels_array = data["labels"].split(',')
        labels = dict(s.split('=') for s in labels_array)
        meta.labels = labels

    envs = []
    if data.has_key("environments"):
        envs_array = data["environments"].splitlines()
        tmp_envs = dict(s.split('=', 1) for s in envs_array)
        for key in tmp_envs:
            envs.append(client.V1EnvVar(name=key, value=tmp_envs[key]))

    if data.has_key("environments_secrets"):
        envs_array = data["environments_secrets"].splitlines()
        tmp_envs = dict(s.split('=', 1) for s in envs_array)

        for key in tmp_envs:

            if (":" in tmp_envs[key]):
                # passing secret env
                value = tmp_envs[key]
                secrets = value.split(':')
                secrect_key = secrets[1]
                secrect_name = secrets[0]

                envs.append(client.V1EnvVar(name=key,
                                            value="",
                                            value_from=client.V1EnvVarSource(
                                                secret_key_ref=client.V1SecretKeySelector(key=secrect_key,
                                                                                          name=secrect_name))))


    log.debug(envs)

    container = client.V1Container(name=data["container_name"],
                                   image=data["container_image"],image_pull_policy=data["image_pull_policy"])

    if(data.has_key("container_command")):
        container.command = data["container_command"].split(' ')

    if (data.has_key("container_args")):
        args_array = data["container_args"].splitlines()
        container.args = args_array

    if (data.has_key("resources_requests")):
        resources_array = data["resources_requests"].split(",")
        tmp_resources = dict(s.split('=', 1) for s in resources_array)
        container.resources = client.V1ResourceRequirements(requests=tmp_resources)


    if (data.has_key("volumes")):
        volumes_array = data["resources_requests"].splitlines()
        tmp_volumes = dict(s.split('=', 1) for s in volumes_array)

        mounts=[]
        for key in tmp_volumes:
            mounts.append(client.V1VolumeMount(name=key, mount_path=tmp_volumes[key]) )

        container.volume_mounts = mounts

    container.env = envs

    template_spec = client.V1PodSpec(
        containers=[
            container
        ], restart_policy=data["job_restart_policy"])


    template = client.V1PodTemplateSpec(metadata=client.V1ObjectMeta(name=data["name"]),
                                                                     spec=template_spec)

    spec = client.V1JobSpec(template=template)

    if(data.has_key("completions")):
        spec.completions = int(data["completions"])
    if (data.has_key("selectors")):
        selectors_array = data["selectors"].split(',')
        selectors = dict(s.split('=') for s in selectors_array)
        spec.selector = selectors
    if (data.has_key("parallelism")):
        spec.parallelism = int(data["parallelism"])
    if (data.has_key("active_deadline_seconds")):
        spec.active_deadline_seconds = int(data["active_deadline_seconds"])

    job = client.V1Job(api_version=data["api_version"], kind='Job', metadata=meta, spec=spec)

    return job

def main():


    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    connect()

    data={}
    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')
    data["container_name"] = os.environ.get('RD_CONFIG_CONTAINER_NAME')
    data["container_image"] = os.environ.get('RD_CONFIG_CONTAINER_IMAGE')

    data["image_pull_policy"]= os.environ.get('RD_CONFIG_IMAGE_PULL_POLICY')

    if os.environ.get('RD_CONFIG_PARALLELISM'):
        data["parallelism"] = os.environ.get('RD_CONFIG_PARALLELISM')

    if os.environ.get('RD_CONFIG_LABELS'):
        data["labels"] = os.environ.get('RD_CONFIG_LABELS')

    if os.environ.get('RD_CONFIG_SELECTORS'):
        data["selectors"] = os.environ.get('RD_CONFIG_SELECTORS')

    if os.environ.get('RD_CONFIG_CONTAINER_COMMAND'):
        data["container_command"] = os.environ.get('RD_CONFIG_CONTAINER_COMMAND')

    if os.environ.get('RD_CONFIG_CONTAINER_ARGS'):
        data["container_args"]=os.environ.get('RD_CONFIG_CONTAINER_ARGS')

    if os.environ.get('RD_CONFIG_RESOURCES_REQUESTS'):
        data["resources_requests"]=os.environ.get('RD_CONFIG_RESOURCES_REQUESTS')

    if os.environ.get('RD_CONFIG_VOLUMES'):
        data["volumes"]=os.environ.get('RD_CONFIG_VOLUMES')

    if os.environ.get('RD_CONFIG_JOB_RESTART_POLICY'):
        data["job_restart_policy"] = os.environ.get('RD_CONFIG_JOB_RESTART_POLICY')

    if os.environ.get('RD_CONFIG_COMPLETIONS'):
        data["completions"] = os.environ.get('RD_CONFIG_COMPLETIONS')

    if os.environ.get('RD_CONFIG_ACTIVE_DEADLINE_SECONDS'):
        data["active_deadline_seconds"] = os.environ.get('RD_CONFIG_ACTIVE_DEADLINE_SECONDS')

    if os.environ.get('RD_CONFIG_ENVIRONMENTS'):
        data["environments"] = os.environ.get('RD_CONFIG_ENVIRONMENTS')

    if os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS'):
        data["environments_secrets"] = os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS')

    log.debug("Creating job")
    log.debug(data)

    job= create_job_object(data)

    log.debug("new job: ")
    log.debug(job)

    try:

        k8s_client = client.BatchV1Api()
        api_response = k8s_client.create_namespaced_job(body=job, namespace=data["namespace"])
        print("Job created. status='%s'" % str(api_response.status))


    except ApiException as e:
        log.error("Exception creating job: %s\n" % e)
        sys.exit(1)



if __name__ == '__main__':
    main()
