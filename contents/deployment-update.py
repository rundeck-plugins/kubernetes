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


def load_liveness_readiness_probe(data):
    probe = yaml.load(data)

    httpGet = None

    if probe.has_key("httpGet"):
        if probe['httpGet'].has_key("port"):
            httpGet = client.V1HTTPGetAction(port=int(probe['httpGet']['port']))
            if probe['httpGet'].has_key("path"):
                httpGet.path = probe['httpGet']['path']
            if probe['httpGet'].has_key("host"):
                httpGet.host = probe['httpGet']['host']

    execLiveness = None
    if probe.has_key("exec"):
        if probe['exec']['command']:
            execLiveness = client.V1ExecAction(command=probe['exec']['command'])

    v1Probe = client.V1Probe()
    if httpGet:
        v1Probe.http_get = httpGet
    if execLiveness:
        v1Probe._exec = execLiveness

    if probe.has_key("initialDelaySeconds"):
        v1Probe.initial_delay_seconds = probe["initialDelaySeconds"]

    if probe.has_key("periodSeconds"):
        v1Probe.period_seconds = probe["periodSeconds"]

    if probe.has_key("timeoutSeconds"):
        v1Probe.timeout_seconds = probe["timeoutSeconds"]

    return v1Probe

def create_deployment_object(data):
    # Configureate Pod template container

    ports = []

    if data.has_key("ports"):
        for port in data["ports"].split(','):
            portDefinition = client.V1ContainerPort(container_port=int(port))
            ports.append(portDefinition)

    envs = []

    if data.has_key("environments"):
        envs_array = data["environments"].splitlines()
        tmp_envs = dict(s.split('=') for s in envs_array)

        for key in tmp_envs:
            envs.append(client.V1EnvVar(name=key, value=tmp_envs[key]))

    if data.has_key("environments_secrets"):
        envs_array = data["environments_secrets"].splitlines()
        tmp_envs = dict(s.split('=') for s in envs_array)

        for key in tmp_envs:

            if(":" in tmp_envs[key]):
                #passing secret env
                value = tmp_envs[key]
                secrets = value.split(':')
                secrect_key=secrets[1]
                secrect_name = secrets[0]

                envs.append(client.V1EnvVar(name=key,
                                            value="",
                                            value_from=client.V1EnvVarSource(
                                                secret_key_ref=client.V1SecretKeySelector(key=secrect_key,
                                                                              name=secrect_name))))

    container = client.V1Container(
        name=data["container_name"],
        image=data["image"],
        ports=ports,
        env=envs
    )

    if data.has_key("liveness_probe"):
        container.liveness_probe=load_liveness_readiness_probe(data["liveness_probe"])

    if data.has_key("readiness_probe"):
        container.readiness_probe=load_liveness_readiness_probe(data["readiness_probe"])

    if(data.has_key("container_command")):
        container.command = data["container_command"].split(' ')

    if (data.has_key("container_args")):
        args_array = data["container_args"].splitlines()
        container.args = args_array

    if (data.has_key("resources_requests")):
        resources_array = data["resources_requests"].split(",")
        tmp_resources = dict(s.split('=', 1) for s in resources_array)
        container.resources = client.V1ResourceRequirements(requests=tmp_resources)

    labels=None
    if data.has_key("labels"):
        labels_array = data["labels"].split(',')
        labels = dict(s.split('=') for s in labels_array)

    # Create and configurate a spec section
    template = client.V1PodTemplateSpec(
        spec=client.V1PodSpec(containers=[container])
    )
    if labels:
        template.metadata=client.V1ObjectMeta(labels=labels)


    # Create the specification of deployment
    spec = client.ExtensionsV1beta1DeploymentSpec(
        replicas=int(data["replicas"]),
        template=template)
    # Instantiate the deployment object
    deployment = client.ExtensionsV1beta1Deployment(
        api_version=data["api_version"],
        kind="Deployment",
        metadata=client.V1ObjectMeta(labels=labels,namespace=data["namespace"], name=data["name"]),
        spec=spec)

    return deployment


def update_deployment(api_instance, deployment,data):
    # Update the deployment
    api_response = api_instance.patch_namespaced_deployment(
        name=data["name"],
        namespace=data["namespace"],
        body=deployment)
    print("Deployment updated. status='%s'" % str(api_response.status))


def main():


    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")


    data={}

    data["api_version"] = os.environ.get('RD_CONFIG_API_VERSION')
    data["name"]=os.environ.get('RD_CONFIG_NAME')
    data["container_name"] = os.environ.get('RD_CONFIG_CONTAINER_NAME')
    data["image"] = os.environ.get('RD_CONFIG_IMAGE')
    if os.environ.get('RD_CONFIG_PORTS'):
        data["ports"]=os.environ.get('RD_CONFIG_PORTS')

    data["replicas"] = os.environ.get('RD_CONFIG_REPLICAS')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    if os.environ.get('RD_CONFIG_LABELS'):
        data["labels"] = os.environ.get('RD_CONFIG_LABELS')

    if os.environ.get('RD_CONFIG_ENVIRONMENTS'):
        data["environments"]=os.environ.get('RD_CONFIG_ENVIRONMENTS')

    if os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS'):
        data["environments_secrets"]=os.environ.get('RD_CONFIG_ENVIRONMENTS_SECRETS')

    if os.environ.get('RD_CONFIG_LIVENESS_PROBE'):
        data["liveness_probe"]=os.environ.get('RD_CONFIG_LIVENESS_PROBE')

    if os.environ.get('RD_CONFIG_READINESS_PROBE'):
        data["readiness_probe"]=os.environ.get('RD_CONFIG_READINESS_PROBE')

    if os.environ.get('RD_CONFIG_CONTAINER_COMMAND'):
        data["container_command"] = os.environ.get('RD_CONFIG_CONTAINER_COMMAND')

    if os.environ.get('RD_CONFIG_CONTAINER_ARGS'):
        data["container_args"]=os.environ.get('RD_CONFIG_CONTAINER_ARGS')

    if os.environ.get('RD_CONFIG_RESOURCES_REQUESTS'):
        data["resources_requests"]=os.environ.get('RD_CONFIG_RESOURCES_REQUESTS')

    log.debug("Updating Deployment data:")
    log.debug(data)

    connect()

    try:
        extensions_v1beta1 = client.ExtensionsV1beta1Api()
        deployment = create_deployment_object(data)

        log.debug("deployment object: ")
        log.debug(deployment)


        update_deployment(extensions_v1beta1, deployment,data)
    except ApiException as e:
        log.error("Exception updating deployment: %s\n" % e)
        sys.exit(1)

if __name__ == '__main__':
    main()
