import json
import logging
import sys
import os
import tarfile
from tempfile import TemporaryFile

import yaml
import datetime

from kubernetes import client, config
from kubernetes.client import Configuration
from kubernetes.stream import stream
from kubernetes.client.apis import core_v1_api

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-plugin')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)

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
        token = os.environ.get('RD_CONFIG_TOKEN')

    log.debug("config file")
    log.debug(config_file)
    log.debug("-------------------")

    if config_file:
        log.debug("getting settings from file %s" % config_file)
        config.load_kube_config(config_file=config_file)
    else:

        if url:
            log.debug("getting settings from pluing configuration")

            configuration = Configuration()
            configuration.host = url

            if verify_ssl == 'true':
                configuration.verify_ssl = verify_ssl
            else:
                configuration.verify_ssl = None

            if ssl_ca_cert:
                configuration.ssl_ca_cert = ssl_ca_cert

            configuration.api_key['authorization'] = token
            configuration.api_key_prefix['authorization'] = 'Bearer'

            client.Configuration.set_default(configuration)
        else:
            log.debug("getting from default config file")
            config.load_kube_config()

    c = Configuration()
    c.assert_hostname = False
    Configuration.set_default(c)


def load_liveness_readiness_probe(data):
    probe = yaml.load(data)

    httpGet = None

    if "httpGet" in probe:
        if "port" in probe['httpGet']:
            httpGet = client.V1HTTPGetAction(
                port=int(probe['httpGet']['port'])
            )
            if "path" in probe['httpGet']:
                httpGet.path = probe['httpGet']['path']
            if "host" in probe['httpGet']:
                httpGet.host = probe['httpGet']['host']

    execLiveness = None
    if "exec" in probe:
        if probe['exec']['command']:
            execLiveness = client.V1ExecAction(
                command=probe['exec']['command']
            )

    v1Probe = client.V1Probe()
    if httpGet:
        v1Probe.http_get = httpGet
    if execLiveness:
        v1Probe._exec = execLiveness

    if "initialDelaySeconds" in probe:
        v1Probe.initial_delay_seconds = probe["initialDelaySeconds"]

    if "periodSeconds" in probe:
        v1Probe.period_seconds = probe["periodSeconds"]

    if "timeoutSeconds" in probe:
        v1Probe.timeout_seconds = probe["timeoutSeconds"]

    return v1Probe


def parsePorts(data):
    ports = yaml.load(data)
    portsList = []

    if (isinstance(ports, list)):
        for x in ports:

            if "port" in x:
                port = client.V1ServicePort(port=int(x["port"]))

                if "name" in x:
                    port.name = x["name"]
                else:
                    port.name = str.lower(x["protocol"] + str(x["port"]))
                if "node_port" in x:
                    port.node_port = x["node_port"]
                if "protocol" in x:
                    port.protocol = x["protocol"]
                if "targetPort" in x:
                    port.target_port = int(x["targetPort"])

                portsList.append(port)
    else:
        x = ports
        port = client.V1ServicePort(port=int(x["port"]))

        if "node_port" in x:
            port.node_port = x["node_port"]
        if "protocol" in x:
            port.protocol = x["protocol"]
        if "targetPort" in x:
            port.target_port = int(x["targetPort"])

        portsList.append(port)

    return portsList


def create_volume(volume_data):
    if "name" in volume_data:
        volume = client.V1Volume(
            name=volume_data["name"]
        )

        # persistent claim
        if "persistentVolumeClaim" in volume_data:
            volume_pvc = volume_data["persistentVolumeClaim"]
            if "claimName" in volume_pvc:
                pvc = client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=volume_pvc["claimName"]
                )
                volume.persistent_volume_claim = pvc

        # hostpath
        if "hostPath" in volume_data and "path" in volume_data["hostPath"]:
            host_path = client.V1HostPathVolumeSource(
                path=volume_data["hostPath"]["path"]
            )

            if "hostPath" in volume_data and "type" in volume_data["hostPath"]:
                host_path.type = volume_data["hostPath"]["type"]
                volume.host_path = host_path
        # nfs
        if ("nfs" in volume_data and
                "path" in volume_data["nfs"] and
                "server" in volume_data["nfs"]):
            volume.nfs = client.V1NFSVolumeSource(
                path=volume_data["nfs"]["path"],
                server=volume_data["nfs"]["server"]
            )

        return volume

    return None


class ObjectEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return {k.lstrip('_'): v for k, v in vars(obj).items()}


def parseJson(obj):
    return json.dumps(obj, cls=ObjectEncoder)


def create_pod_template_spec(data):
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

            if (":" in tmp_envs[key]):
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
        container.liveness_probe = load_liveness_readiness_probe(
            data["liveness_probe"]
        )

    if "readiness_probe" in data:
        container.readiness_probe = load_liveness_readiness_probe(
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

    template_spec = client.V1PodSpec(
        containers=[container]
    )

    if "volumes" in data:
        volumes_data = yaml.load(data["volumes"])
        volumes = []

        if (isinstance(volumes_data, list)):
            for volume_data in volumes_data:
                volume = create_volume(volume_data)

                if volume:
                    volumes.append(volume)
        else:
            volume = create_volume(volumes_data)

            if volume:
                volumes.append(volume)

        template_spec.volumes = volumes

    return template_spec


def copy_file(name, container, source_file, destination_path, destination_file_name, stdout = False):
    api = core_v1_api.CoreV1Api()

    # Copying file client -> pod
    exec_command = ['tar', 'xvf', '-', '-C', '/']
    resp = stream(api.connect_get_namespaced_pod_exec, name, 'default',
                  command=exec_command,
                  container=container,
                  stderr=False, stdin=True,
                  stdout=False, tty=False,
                  _preload_content=False)

    with TemporaryFile() as tar_buffer:
        with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
            tar.add(name=source_file, arcname=destination_path + "/" + destination_file_name)

        tar_buffer.seek(0)
        commands = []
        commands.append(tar_buffer.read())

        while resp.is_open():
            resp.update(timeout=1)

            if resp.peek_stdout():
                if stdout:
                    log.info("%s" % resp.read_stdout())
            if resp.peek_stderr():
                log.error("ERROR: %s" % resp.read_stderr())
            if commands:
                c = commands.pop(0)
                resp.write_stdin(c)
            else:
                break
        resp.close()


def run_command(name, namespace, container, command):
    api = core_v1_api.CoreV1Api()

    # Calling exec interactively.
    resp = stream(api.connect_get_namespaced_pod_exec,
                  name=name,
                  namespace=namespace,
                  container=container,
                  command=command,
                  stderr=True,
                  stdin=True,
                  stdout=True,
                  tty=True,
                  _preload_content=False
                  )

    resp.run_forever()

    return resp



def run_interactive_command(name, namespace, container, command):
    api = core_v1_api.CoreV1Api()

    # Calling exec interactively.
    resp = stream(api.connect_get_namespaced_pod_exec,
                  name=name,
                  namespace=namespace,
                  container=container,
                  command=command,
                  stderr=True,
                  stdin=True,
                  stdout=True,
                  tty=False,
                  _preload_content=False
                  )

    error = False
    while resp.is_open():
        resp.update(timeout=1)

        if resp.peek_stdout():
            print("%s" % resp.read_stdout())
        if resp.peek_stderr():
            log.error("%s" % resp.read_stderr())
            error = True

    return (resp,error)


def delete_pod(api, data):
    body = client.V1DeleteOptions()

    try:
        resp = api.delete_namespaced_pod(name=data["name"],
                                         namespace=data["namespace"],
                                         pretty="True",
                                         body=body,
                                         grace_period_seconds=5,
                                         propagation_policy='Foreground')

        return resp

    except Exception as e:
        if e.status != 404:
            print("Unknown error: %s" % e)
            return None
