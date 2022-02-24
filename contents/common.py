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
from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-plugin')

PY = sys.version_info[0]

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)


def connect():
    config_file = None

    if os.environ.get('RD_CONFIG_ENV') == 'incluster':
        config.load_incluster_config()
        return

    if os.environ.get('RD_CONFIG_CONFIG_FILE'):
        config_file = os.environ.get('RD_CONFIG_CONFIG_FILE')
    elif os.environ.get('RD_NODE_KUBERNETES_CONFIG_FILE'):
        config_file = os.environ.get('RD_NODE_KUBERNETES_CONFIG_FILE')

    verify_ssl = os.environ.get('RD_CONFIG_VERIFY_SSL')
    ssl_ca_cert = os.environ.get('RD_CONFIG_SSL_CA_CERT')
    url = os.environ.get('RD_CONFIG_URL')

    token = os.environ.get('RD_CONFIG_TOKEN')
    if not token:
        token = os.environ.get('RD_CONFIG_TOKEN_STORAGE_PATH')

    log.debug("config file")
    log.debug(config_file)
    log.debug("-------------------")

    if config_file:
        log.debug("getting settings from file %s", config_file)
        config.load_kube_config(config_file=config_file)
    else:
        if url and token:
            log.debug("getting settings from plugin configuration")

            configuration = Configuration()
            configuration.host = url

            if verify_ssl == 'true':
                configuration.verify_ssl = verify_ssl
            else:
                configuration.verify_ssl = None
                configuration.assert_hostname = False

            if ssl_ca_cert:
                configuration.ssl_ca_cert = ssl_ca_cert

            configuration.api_key['authorization'] = token
            configuration.api_key_prefix['authorization'] = 'Bearer'

            client.Configuration.set_default(configuration)
        else:
            log.debug("Either URL or Token is not defined. Fall back to getting settings from default config file [$home/.kube/config]")
            config.load_kube_config()


def load_liveness_readiness_probe(data):
    probe = yaml.safe_load(data)

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


def get_core_node_parameter_list():
    """
    Finds pod and container request info.

    For pod name and namespace, looks for an explicitly specified value in the
    step definition, and uses the node value if no explicit setting is found.
    When creating nodes, uses 'default' as the namespace when one is not
    specified.

    :returns: A list of name, namespace, and container
    """
    data = get_code_node_parameter_dictionary()
    return [data['name'], data['namespace'], data['container_name']]


def get_code_node_parameter_dictionary():
    """
    Finds pod and container request info.

    For pod name and namespace, looks for an explicitly specified value in the
    step definition, and uses the node value if no explicit setting is found.
    When creating nodes, uses 'default' as the namespace when one is not
    specified.

    :returns: A dictionary of name, namespace, and container
    """
    container = None

    if 'RD_CONFIG_CONTAINER_NAME' in os.environ:
        container = os.environ.get('RD_CONFIG_CONTAINER_NAME')

    if container is None and 'RD_CONFIG_CONTAINER' in os.environ:
        container = os.environ.get('RD_CONFIG_CONTAINER')

    if container is None and 'RD_NODE_DEFAULT_CONTAINER_NAME' in os.environ:
        container = os.environ.get('RD_NODE_DEFAULT_CONTAINER_NAME')

    return {
        'name': os.environ.get('RD_CONFIG_NAME', os.environ.get('RD_NODE_DEFAULT_NAME')),
        'namespace': os.environ.get('RD_CONFIG_NAMESPACE', os.environ.get('RD_NODE_DEFAULT_NAMESPACE', 'default')),
        'container_name': container
    }


def log_pod_parameters(logger, data):
    """Writes debug-level log for a pod."""
    logger.debug("--------------------------")
    logger.debug("Pod Name:  %s", data['name'])
    logger.debug("Namespace: %s", data['namespace'])
    logger.debug("Container: %s", data['container_name'])
    logger.debug("--------------------------")


def resolve_container_for_pod(name, namespace):
    core_v1 = client.CoreV1Api()
    response = core_v1.read_namespaced_pod_status(
        name=name,
        namespace=namespace,
        pretty="True"
    )

    if response.spec.containers:
        container = response.spec.containers[0].name
        return container
    log.error("Container not found for pod %s", name)
    exit(1)


def get_active_pods_for_deployment(name, namespace):
    """
    Retrieve all pods belonging to a deployment
    """
    api = core_v1_api.CoreV1Api()
    resp = None
    try:
        resp = api.list_namespaced_pod(namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            log.exception("Unknown error:")
            exit(1)

    if not resp:
        log.error("Namespace %s does not exits.", namespace)
        exit(1)
    pods_for_deployment = []
    for pod_spec in resp.items:
        pod_labels = pod_spec.metadata.labels
        if pod_labels['app'] == name and pod_spec.status.phase == 'Running':
            pods_for_deployment.append(pod_spec.metadata.name)
    if len(pods_for_deployment) < 1:
        log.error("Did not find valid pods for deployment %s in namespace %s", name, namespace)
        exit(1)
    return pods_for_deployment


def verify_pod_exists(name, namespace):
    """Verify pod exists."""
    api = core_v1_api.CoreV1Api()
    resp = None
    try:
        resp = api.read_namespaced_pod(name=name, namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            log.exception("Unknown error:")
            exit(1)
    if not resp:
        log.error("Pod %s does not exist", name)
        exit(1)


def parsePorts(data):
    ports = yaml.safe_load(data)
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
            host_path = client.V1HostPathVolumeSource(path=volume_data["hostPath"]["path"])
            if "type" in volume_data["hostPath"]:
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

        # secret
        if "secret" in volume_data:
            volume.secret = client.V1SecretVolumeSource(
                secret_name=volume_data["secret"]["secretName"]
            )

        # configMap
        if "configMap" in volume_data:
            volume.config_map = client.V1ConfigMapVolumeSource(
                name=volume_data["configMap"]["name"]
            )

        return volume

    return None


def create_volume_mount(volume_mount_data):
    if "name" in volume_mount_data and "mountPath" in volume_mount_data:
        volume_mount = client.V1VolumeMount(
            name=volume_mount_data["name"],
            mount_path=volume_mount_data["mountPath"]
        )
        if "subPath" in volume_mount_data:
            volume_mount.sub_path = volume_mount_data["subPath"]

        if "readOnly" in volume_mount_data:
            volume_mount.read_only = volume_mount_data["readOnly"]

        return volume_mount

    return None


def create_toleration(toleration_data):
    toleration = client.V1Toleration()

    if "effect" in toleration_data:
        toleration.effect = toleration_data["effect"]
    if "key" in toleration_data:
        toleration.key = toleration_data["key"]
    if "operator" in toleration_data:
        toleration.operator = toleration_data["operator"]
    if "value" in toleration_data:
        toleration.value = toleration_data["value"]
    if "toleration_seconds" in toleration_data:
        toleration.toleration_seconds = int(toleration_data["toleration_seconds"])

    return toleration


class ObjectEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return {k.lstrip('_'): v for k, v in vars(obj).items()}


def parseJson(obj):
    try:
        return json.dumps(obj, cls=ObjectEncoder)
    except:
        return obj


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
                secret_key = secrets[1]
                secret_name = secrets[0]

                envs.append(client.V1EnvVar(
                    name=key,
                    value="",
                    value_from=client.V1EnvVarSource(
                        secret_key_ref=client.V1SecretKeySelector(
                            key=secret_key,
                            name=secret_name))
                )
                )

    container = client.V1Container(
        name=data["container_name"],
        image=data["image"],
        ports=ports,
        env=envs
    )

    if "volume_mounts" in data:
        container.volume_mounts = create_volume_mount_yaml(data)

    if "liveness_probe" in data:
        container.liveness_probe = load_liveness_readiness_probe(
            data["liveness_probe"]
        )

    if "readiness_probe" in data:
        container.readiness_probe = load_liveness_readiness_probe(
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

    template_spec = client.V1PodSpec(
        containers=[container]
    )

    if "image_pull_secrets" in data:
        images_array = data["image_pull_secrets"].split(",")
        images = []
        for image in images_array:
            images.append(client.V1LocalObjectReference(name=image))

        template_spec.image_pull_secrets = images

    if "volumes" in data:
        volumes_data = yaml.safe_load(data["volumes"])
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


def create_volume_mount_yaml(data):
    volume_mounts_data = yaml.safe_load(data["volume_mounts"])
    volume_mounts = []

    if (isinstance(volume_mounts_data, list)):
        for volume_mount_data in volume_mounts_data:
            volume_mount = create_volume_mount(volume_mount_data)

            if volume_mount:
                volume_mounts.append(volume_mount)
    else:
        volume_mount = create_volume_mount(volume_mounts_data)

        if volume_mount:
            volume_mounts.append(volume_mount)

    return volume_mounts


def copy_file(name, namespace, container, source_file, destination_path, destination_file_name, stdout=False):
    api = core_v1_api.CoreV1Api()

    # Copying file client -> pod
    exec_command = ['tar', 'xvf', '-', '-C', '/']
    resp = stream(api.connect_get_namespaced_pod_exec, name, namespace,
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
                    log.info("%s", resp.read_stdout())
            if resp.peek_stderr():
                log.error("ERROR: %s", resp.read_stderr())
            if commands:
                c = commands.pop(0)

                # Python 3 expects bytes string to transfer the data.
                if PY == 3:
                    c = c.decode()
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
            print(resp.read_stderr())

    ERROR_CHANNEL = 3
    err = api.api_client.last_response.read_channel(ERROR_CHANNEL)
    err = yaml.safe_load(err)
    if err['status'] != "Success":
        log.error('Failed to run command')
        log.error('Reason: ' + err['reason'])
        log.error('Message: ' + err['message'])
        log.error('Details: ' + ';'.join(map(lambda x: json.dumps(x), err['details']['causes'])))
        error = True

    return (resp, error)


def delete_pod(data):
    api = core_v1_api.CoreV1Api()
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
            log.exception("Unknown error:")
            return None
