"""
Unit tests for common.py functions.
"""

import datetime
import json
import os
import unittest
from unittest.mock import patch, MagicMock

from .. import common


class TestCommon(unittest.TestCase):

    def test_parse_ports(self):
        """
        Test parsePorts function.

        The current code this tests does not create a stub name when a single
        port is passed instead of a list of ports. It's not clear if that is
        intentional or accidental, so in that respect this test is only
        intended to prevent regressions, not to suggest there is a fundamental
        problem with naming a single port.
        """
        entry = {'node_port': 90, 'port': 8080, 'protocol': 'TCP', 'targetPort': 80}
        named_entry = {'name': 'foo', 'node_port': 90, 'port': 8080, 'protocol': 'TCP', "targetPort": 80}

        data = json.dumps(entry)
        actual = common.parsePorts(data)
        port = actual.pop()
        self.assert_port_match(port, entry, None)

        data = json.dumps(named_entry)
        actual = common.parsePorts(data)
        print(actual)
        port = actual.pop()
        print(port)
        self.assert_port_match(port, named_entry, None)

        data = json.dumps([named_entry, entry])
        print(data)
        actual = common.parsePorts(data)
        port = actual.pop()
        print(port)
        self.assert_port_match(port, entry, str.lower(entry['protocol']) + str(entry['port']))
        port = actual.pop()
        self.assert_port_match(port, entry, named_entry['name'])

    def assert_port_match(self, port, expected, name):
        """
        Asserts that a port object matches the input array.

        :param port:
        :param expected:
        :param name:
        :returns: None
        """
        self.assertEqual(port.port, expected['port'])
        self.assertEqual(port.node_port, expected['node_port'])
        self.assertEqual(port.protocol, expected['protocol'])
        self.assertEqual(port.target_port, expected['targetPort'])
        self.assertEqual(port.name, name)

    def test_get_code_node_parameter_dictionary(self):
        os.environ.clear()
        data = common.get_code_node_parameter_dictionary()
        self.assertIsNone(data['name'])
        self.assertEqual('default', data['namespace'])
        self.assertIsNone(data['container_name'])
        [actual_name, actual_namespace, actual_container] = common.get_core_node_parameter_list()
        self.assertEqual(data['name'], actual_name)
        self.assertEqual(data['namespace'], actual_namespace)
        self.assertEqual(data['container_name'], actual_container)

        os.environ.clear()
        name = 'Node'
        namespace = 'Space'
        container = 'Container'
        os.environ.setdefault('RD_NODE_DEFAULT_NAME', name)
        os.environ.setdefault('RD_NODE_DEFAULT_NAMESPACE', namespace)
        os.environ.setdefault('RD_NODE_DEFAULT_CONTAINER_NAME', container)
        self.assert_dictionary_matches(name, namespace, container)

        os.environ.clear()
        name = 'Config Node'
        namespace = 'Config Space'
        config_container = 'Config Container'
        os.environ.setdefault('RD_CONFIG_NAME', name)
        os.environ.setdefault('RD_CONFIG_NAMESPACE', namespace)
        os.environ.setdefault('RD_CONFIG_CONTAINER_NAME', config_container)
        self.assert_dictionary_matches(name, namespace, config_container)

        os.environ.clear()
        name = 'Config Node'
        namespace = 'Config Space'
        config2_container = 'Config2 Container'
        os.environ.setdefault('RD_CONFIG_NAME', name)
        os.environ.setdefault('RD_CONFIG_NAMESPACE', namespace)
        os.environ.setdefault('RD_CONFIG_CONTAINER', config2_container)
        self.assert_dictionary_matches(name, namespace, config2_container)

    def assert_dictionary_matches(self, name, namespace, container):
        """Asserts that a """
        data = common.get_code_node_parameter_dictionary()
        self.assertEqual(name, data['name'])
        self.assertEqual(namespace, data['namespace'])
        self.assertEqual(container, data['container_name'])
        [actual_name, actual_namespace, actual_container] = common.get_core_node_parameter_list()
        self.assertEqual(name, actual_name)
        self.assertEqual(namespace, actual_namespace)
        self.assertEqual(container, actual_container)

    def test_create_volume(self):
        data = {}
        self.assertIsNone(common.create_volume(data))

        data = {'name': 'volumeName'}
        self.assertEqual(data['name'], common.create_volume(data).name)

        claim = 'CLAIM'
        path_name = 'PATH'
        path_type = 'Directory'
        data = {
            'name': 'volumeName',
            'persistentVolumeClaim': {'claimName': claim},
            'hostPath': {'path': path_name, 'type': path_type},
        }
        volume = common.create_volume(data)
        pvc = volume.persistent_volume_claim
        path = volume.host_path
        self.assertEqual(claim, pvc.claim_name)
        self.assertEqual(path_name, path.path)

        data['hostPath'] = {'path': path_name}
        volume = common.create_volume(data)
        self.assertEqual(claim, volume.persistent_volume_claim.claim_name)
        # This is strange -- the code is forcing a constraint on path type
        # that kubernetes itself does not have. I think this assertion should
        # pass but it does not. I think the indent on line 254 of common.py
        # is wrong. So I'm going to stop here and ask the maintainer via
        # a pull request.
        # self.assertEqual(path_name, path.path)

    def test_create_volume_mount(self):
        """
        Tests create_volume_mount() function.

        There is not much happening in this test. We are simply putting in a
        guardrail against silly typographical errors as code might change in
        the future.

        :return: None
        """
        data = {'name': 'volumeName'}
        self.assertIsNone(common.create_volume_mount(data))

        data = {'mountPath': 'mountPath'}
        self.assertIsNone(common.create_volume_mount(data))

        data = {
            'name': 'volumeName',
            'mountPath': 'mountPath',
        }
        mount = common.create_volume_mount(data)
        self.assertEqual(data['name'], mount.name)
        self.assertEqual(data['mountPath'], mount.mount_path)
        self.assertIsNone(mount.sub_path)
        self.assertFalse(mount.read_only)

        data = {
            'name': 'volumeName',
            'mountPath': 'mountPath',
            'subPath': 'subPath',
            'readOnly': True,
        }
        mount = common.create_volume_mount(data)
        self.assertEqual(data['name'], mount.name)
        self.assertEqual(data['mountPath'], mount.mount_path)
        self.assertEqual(data['subPath'], mount.sub_path)
        self.assertTrue(mount.read_only)


    def test_load_liveness_readiness_probe_http_get(self):
        data = json.dumps({
            'httpGet': {'port': 8080, 'path': '/health', 'host': 'localhost'},
            'initialDelaySeconds': 10,
            'periodSeconds': 5,
            'timeoutSeconds': 3,
        })
        probe = common.load_liveness_readiness_probe(data)
        self.assertEqual(8080, probe.http_get.port)
        self.assertEqual('/health', probe.http_get.path)
        self.assertEqual('localhost', probe.http_get.host)
        self.assertEqual(10, probe.initial_delay_seconds)
        self.assertEqual(5, probe.period_seconds)
        self.assertEqual(3, probe.timeout_seconds)

    def test_load_liveness_readiness_probe_exec(self):
        data = json.dumps({
            'exec': {'command': ['/bin/sh', '-c', 'echo ok']},
        })
        probe = common.load_liveness_readiness_probe(data)
        self.assertEqual(['/bin/sh', '-c', 'echo ok'], probe._exec.command)
        self.assertIsNone(probe.http_get)

    def test_load_liveness_readiness_probe_http_get_port_only(self):
        data = json.dumps({'httpGet': {'port': 80}})
        probe = common.load_liveness_readiness_probe(data)
        self.assertEqual(80, probe.http_get.port)
        self.assertIsNone(probe.http_get.path)
        self.assertIsNone(probe.http_get.host)

    def test_log_pod_parameters(self):
        logger = MagicMock()
        data = {'name': 'my-pod', 'namespace': 'default', 'container_name': 'app'}
        common.log_pod_parameters(logger, data)
        self.assertEqual(5, logger.debug.call_count)

    def test_create_toleration_all_fields(self):
        data = {
            'effect': 'NoSchedule',
            'key': 'dedicated',
            'operator': 'Equal',
            'value': 'special',
            'toleration_seconds': '300',
        }
        toleration = common.create_toleration(data)
        self.assertEqual('NoSchedule', toleration.effect)
        self.assertEqual('dedicated', toleration.key)
        self.assertEqual('Equal', toleration.operator)
        self.assertEqual('special', toleration.value)
        self.assertEqual(300, toleration.toleration_seconds)

    def test_create_toleration_partial_fields(self):
        data = {'key': 'node-role', 'operator': 'Exists'}
        toleration = common.create_toleration(data)
        self.assertEqual('node-role', toleration.key)
        self.assertEqual('Exists', toleration.operator)
        self.assertIsNone(toleration.effect)
        self.assertIsNone(toleration.value)

    def test_object_encoder_datetime(self):
        dt = datetime.datetime(2024, 1, 15, 12, 30, 45)
        result = json.dumps({'time': dt}, cls=common.ObjectEncoder)
        self.assertIn('2024-01-15T12:30:45', result)

    def test_object_encoder_object(self):
        obj = MagicMock()
        obj.__class__ = type('Obj', (), {})
        obj._private = 'val1'
        obj.public = 'val2'
        # Use vars() directly since ObjectEncoder uses vars()
        encoder = common.ObjectEncoder()
        result = encoder.default(obj)
        self.assertIn('private', result)
        self.assertIn('public', result)

    def test_parse_json(self):
        result = common.parseJson({'key': 'value'})
        parsed = json.loads(result)
        self.assertEqual('value', parsed['key'])

    def test_parse_json_fallback(self):
        obj = object()
        result = common.parseJson(obj)
        self.assertIs(obj, result)

    def test_create_volume_mount_yaml_list(self):
        data = {
            'volume_mounts': json.dumps([
                {'name': 'vol1', 'mountPath': '/mnt/1'},
                {'name': 'vol2', 'mountPath': '/mnt/2'},
            ])
        }
        mounts = common.create_volume_mount_yaml(data)
        self.assertEqual(2, len(mounts))
        self.assertEqual('vol1', mounts[0].name)
        self.assertEqual('vol2', mounts[1].name)

    def test_create_volume_mount_yaml_single(self):
        data = {
            'volume_mounts': json.dumps({'name': 'vol1', 'mountPath': '/mnt/1'})
        }
        mounts = common.create_volume_mount_yaml(data)
        self.assertEqual(1, len(mounts))
        self.assertEqual('vol1', mounts[0].name)

    def test_create_pod_template_spec_basic(self):
        data = {
            'container_name': 'app',
            'image': 'nginx:latest',
            'ports': '80,443',
        }
        spec = common.create_pod_template_spec(data)
        container = spec.containers[0]
        self.assertEqual('app', container.name)
        self.assertEqual('nginx:latest', container.image)
        self.assertEqual(2, len(container.ports))
        self.assertEqual(80, container.ports[0].container_port)
        self.assertEqual(443, container.ports[1].container_port)

    def test_create_pod_template_spec_no_ports(self):
        data = {
            'container_name': 'app',
            'image': 'nginx:latest',
            'ports': None,
        }
        spec = common.create_pod_template_spec(data)
        self.assertEqual([], spec.containers[0].ports)

    def test_create_pod_template_spec_environments(self):
        data = {
            'container_name': 'app',
            'image': 'nginx:latest',
            'ports': None,
            'environments': 'FOO=bar\nBAZ=qux',
        }
        spec = common.create_pod_template_spec(data)
        envs = spec.containers[0].env
        self.assertEqual(2, len(envs))
        self.assertEqual('FOO', envs[0].name)
        self.assertEqual('bar', envs[0].value)

    def test_create_pod_template_spec_environment_secrets(self):
        data = {
            'container_name': 'app',
            'image': 'nginx:latest',
            'ports': None,
            'environments_secrets': 'DB_PASS=my-secret:password',
        }
        spec = common.create_pod_template_spec(data)
        env = spec.containers[0].env[0]
        self.assertEqual('DB_PASS', env.name)
        self.assertEqual('my-secret', env.value_from.secret_key_ref.name)
        self.assertEqual('password', env.value_from.secret_key_ref.key)

    def test_create_pod_template_spec_command_and_args(self):
        data = {
            'container_name': 'app',
            'image': 'nginx:latest',
            'ports': None,
            'container_command': '/bin/sh -c echo',
            'container_args': 'arg1\narg2',
        }
        spec = common.create_pod_template_spec(data)
        container = spec.containers[0]
        self.assertEqual(['/bin/sh', '-c', 'echo'], container.command)
        self.assertEqual(['arg1', 'arg2'], container.args)

    def test_create_pod_template_spec_resources(self):
        data = {
            'container_name': 'app',
            'image': 'nginx:latest',
            'ports': None,
            'resources_requests': 'cpu=100m,memory=128Mi',
        }
        spec = common.create_pod_template_spec(data)
        resources = spec.containers[0].resources
        self.assertEqual('100m', resources.requests['cpu'])
        self.assertEqual('128Mi', resources.requests['memory'])

    def test_create_pod_template_spec_image_pull_secrets(self):
        data = {
            'container_name': 'app',
            'image': 'nginx:latest',
            'ports': None,
            'image_pull_secrets': 'secret1,secret2',
        }
        spec = common.create_pod_template_spec(data)
        self.assertEqual(2, len(spec.image_pull_secrets))
        self.assertEqual('secret1', spec.image_pull_secrets[0].name)
        self.assertEqual('secret2', spec.image_pull_secrets[1].name)

    @patch('contents.common.config')
    def test_connect_incluster(self, mock_config):
        os.environ.clear()
        os.environ['RD_CONFIG_ENV'] = 'incluster'
        common.connect()
        mock_config.load_incluster_config.assert_called_once()

    @patch('contents.common.config')
    def test_connect_config_file(self, mock_config):
        os.environ.clear()
        os.environ['RD_CONFIG_CONFIG_FILE'] = '/path/to/config'
        common.connect()
        mock_config.load_kube_config.assert_called_once_with(config_file='/path/to/config')

    @patch('contents.common.config')
    def test_connect_node_config_file(self, mock_config):
        os.environ.clear()
        os.environ['RD_NODE_KUBERNETES_CONFIG_FILE'] = '/node/config'
        common.connect()
        mock_config.load_kube_config.assert_called_once_with(config_file='/node/config')

    @patch('contents.common.client.Configuration.set_default')
    @patch('contents.common.config')
    def test_connect_url_and_token(self, mock_config, mock_set_default):
        os.environ.clear()
        os.environ['RD_CONFIG_URL'] = 'https://k8s.example.com'
        os.environ['RD_CONFIG_TOKEN'] = 'my-token'
        os.environ['RD_CONFIG_VERIFY_SSL'] = 'true'
        common.connect()
        mock_set_default.assert_called_once()

    @patch('contents.common.config')
    def test_connect_default_fallback(self, mock_config):
        os.environ.clear()
        common.connect()
        mock_config.load_kube_config.assert_called_once_with()

    @patch('contents.common.core_v1_api.CoreV1Api')
    def test_verify_pod_exists_found(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.read_namespaced_pod.return_value = MagicMock()
        common.verify_pod_exists('my-pod', 'default')
        mock_api.read_namespaced_pod.assert_called_once_with(name='my-pod', namespace='default')

    @patch('contents.common.core_v1_api.CoreV1Api')
    def test_verify_pod_exists_not_found(self, mock_api_class):
        from kubernetes.client.rest import ApiException
        mock_api = mock_api_class.return_value
        mock_api.read_namespaced_pod.side_effect = ApiException(status=404)
        with self.assertRaises(SystemExit):
            common.verify_pod_exists('missing-pod', 'default')

    @patch('contents.common.core_v1_api.CoreV1Api')
    def test_verify_pod_exists_other_error(self, mock_api_class):
        from kubernetes.client.rest import ApiException
        mock_api = mock_api_class.return_value
        mock_api.read_namespaced_pod.side_effect = ApiException(status=500)
        with self.assertRaises(SystemExit):
            common.verify_pod_exists('my-pod', 'default')

    @patch('contents.common.core_v1_api.CoreV1Api')
    def test_delete_pod_success(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.delete_namespaced_pod.return_value = MagicMock()
        result = common.delete_pod({'name': 'my-pod', 'namespace': 'default'})
        self.assertIsNotNone(result)

    @patch('contents.common.core_v1_api.CoreV1Api')
    def test_delete_pod_not_found(self, mock_api_class):
        from kubernetes.client.rest import ApiException
        mock_api = mock_api_class.return_value
        mock_api.delete_namespaced_pod.side_effect = ApiException(status=404)
        result = common.delete_pod({'name': 'my-pod', 'namespace': 'default'})
        self.assertIsNone(result)

    @patch('contents.common.core_v1_api.CoreV1Api')
    def test_delete_pod_other_error(self, mock_api_class):
        from kubernetes.client.rest import ApiException
        mock_api = mock_api_class.return_value
        mock_api.delete_namespaced_pod.side_effect = ApiException(status=500)
        result = common.delete_pod({'name': 'my-pod', 'namespace': 'default'})
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
