import json
import logging
import sys
import os
import tarfile
import tempfile

import yaml
import datetime

from kubernetes import client, config

from kubernetes.stream import stream
from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException

import urllib3
from urllib3.exceptions import InsecureRequestWarning
urllib3.disable_warnings(InsecureRequestWarning)

LOG_FORMAT = '%(levelname)s: %(name)s: %(message)s'

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger('kubernetes-plugin')


def log_info_to_stdout():
    """Send DEBUG and INFO records to stdout and WARNING and above to stderr.

    Rundeck records every line a step writes to stderr at ERROR level, so
    with all logging on stderr a step's progress messages show as errors,
    and log filters that only act on normal output (key-value-data,
    quiet-output) never see them. Only call this from steps whose stdout
    is read by people: the resource model, node executor, file copier and
    inline script steps keep stdout for the data or command output that
    Rundeck and job authors parse.
    """
    stdout = logging.StreamHandler(sys.stdout)
    stdout.addFilter(lambda record: record.levelno < logging.WARNING)
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setLevel(logging.WARNING)
    logging.basicConfig(handlers=[stdout, stderr], level=logging.INFO,
                        format=LOG_FORMAT, force=True)

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)

# Check kubernetes client version and warn if outdated
try:
    from packaging import version
    from packaging.version import InvalidVersion
except ImportError:
    version = None
    InvalidVersion = None

if version is not None:
    MIN_KUBERNETES_VERSION = "35.0.0"
    try:
        import kubernetes
        current_version = kubernetes.__version__
        try:
            if version.parse(current_version) < version.parse(MIN_KUBERNETES_VERSION):
                log.warning("=" * 80)
                log.warning("SECURITY WARNING: Outdated Kubernetes Python client detected")
                log.warning(f"Current version: {current_version}")
                log.warning(f"Required version: {MIN_KUBERNETES_VERSION}+")
                log.warning("")
                log.warning("Your installation is vulnerable to CVE-2026-23490 (CVSS 7.5 HIGH)")
                log.warning("")
                log.warning("ACTION REQUIRED: Upgrade the kubernetes Python library on the")
                log.warning("server where Rundeck is running (or on your Runner if using")
                log.warning("remote execution):")
                log.warning("")
                log.warning(f"  pip install --upgrade 'kubernetes>={MIN_KUBERNETES_VERSION}'")
                log.warning(f"  # or: pip3 install --upgrade 'kubernetes>={MIN_KUBERNETES_VERSION}'")
                log.warning("")
                log.warning("The plugin will continue to work, but you should upgrade to")
                log.warning("eliminate the security vulnerability.")
                log.warning("=" * 80)
        except InvalidVersion:
            pass
    except (AttributeError, ImportError):
        pass


def connect():
    config_file = None

    if os.environ.get('RD_CONFIG_ENV') == 'incluster':
        config.load_incluster_config()
        return

    config_file = os.environ.get('RD_CONFIG_CONFIG_FILE') or os.environ.get('RD_NODE_KUBERNETES_CONFIG_FILE')

    verify_ssl = os.environ.get('RD_CONFIG_VERIFY_SSL')
    ssl_ca_cert = os.environ.get('RD_CONFIG_SSL_CA_CERT')
    url = os.environ.get('RD_CONFIG_URL')

    token = os.environ.get('RD_CONFIG_TOKEN')
    if not token:
        token = os.environ.get('RD_CONFIG_TOKEN_STORAGE_PATH')

    if config_file:
        log.debug("getting settings from file %s", config_file)
        try:
            config.load_kube_config(config_file=config_file)
        except Exception as e:
            log.error("Failed to load kube config from %s: %s", config_file, e)
            raise
    else:
        if url and token:
            log.debug("getting settings from plugin configuration")

            kubeconfig_dict = {
                'clusters': [{
                    'cluster': {
                        'server': url,
                    },
                    'name': 'rundeck-cluster',
                }],
                'contexts': [{
                    'context': {
                        'cluster': 'rundeck-cluster',
                        'user': 'rundeck-user',
                    },
                    'name': 'rundeck-context',
                }],
                'current-context': 'rundeck-context',
                'users': [{
                    'user': {
                        'token': token,
                    },
                    'name': 'rundeck-user',
                }],
            }

            if verify_ssl == 'true':
                kubeconfig_dict['clusters'][0]['cluster']['insecure-skip-tls-verify'] = False
            else:
                kubeconfig_dict['clusters'][0]['cluster']['insecure-skip-tls-verify'] = True

            if ssl_ca_cert:
                kubeconfig_dict['clusters'][0]['cluster']['certificate-authority'] = ssl_ca_cert

            try:
                config.load_kube_config_from_dict(kubeconfig_dict, persist_config=False)
            except Exception as e:
                log.error("Failed to configure Kubernetes client with URL=%s: %s", url, e)
                raise
        else:
            log.debug("Either URL or Token is not defined. Fall back to getting settings from default config file [$home/.kube/config]")
            try:
                config.load_kube_config()
            except Exception as e:
                log.error("Failed to load default kube config: %s", e)
                raise


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
    container = (os.environ.get('RD_CONFIG_CONTAINER_NAME')
                 or os.environ.get('RD_CONFIG_CONTAINER')
                 or os.environ.get('RD_NODE_DEFAULT_CONTAINER_NAME'))

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


def verify_pod_exists(name, namespace):
    """Verify pod exists."""
    api = core_v1_api.CoreV1Api()
    resp = None
    try:
        resp = api.read_namespaced_pod(name=name, namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            log.exception("Unknown error:")
            sys.exit(1)
    if not resp:
        log.error("Pod %s does not exist", name)
        sys.exit(1)


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
    except Exception:
        return obj


def create_pod_template_spec(data):

    ports = []
    if data["ports"]:
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

    if "resources_limits" in data:
        resources_array = data["resources_limits"].split(",")
        tmp_limits = dict(s.split('=', 1) for s in resources_array)
        if container.resources is not None:
            container.resources.limits = tmp_limits
        else:
            container.resources = client.V1ResourceRequirements(
                limits=tmp_limits
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

    with tempfile.TemporaryFile() as tar_buffer:
        with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
            tar.add(name=source_file, arcname=destination_path + "/" + destination_file_name)

        tar_buffer.seek(0)
        sent = False

        while resp.is_open():
            resp.update(timeout=1)

            if resp.peek_stdout():
                if stdout:
                    log.info("%s", resp.read_stdout())
            if resp.peek_stderr():
                log.error("ERROR: %s", resp.read_stderr())
            if not sent:
                chunk = tar_buffer.read(4096)
                while chunk:
                    resp.write_stdin(chunk)
                    chunk = tar_buffer.read(4096)
                sent = True
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
        log.error('Reason: %s', err['reason'])
        log.error('Message: %s', err['message'])
        log.error('Details: %s', ';'.join(json.dumps(x) for x in err['details']['causes']))
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

    except ApiException as e:
        # A pod that is already gone is not a failure to delete, so report that
        # by returning None. Anything else is raised so the caller can tell the
        # two apart -- returning None for both left callers unable to notice a
        # failed delete.
        if e.status != 404:
            raise
        log.warning("Pod %s not found in namespace %s", data["name"], data["namespace"])
        return None
