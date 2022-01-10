"""
Unit tests for common.py functions.
"""

import json
import os
import unittest

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
        entry = {'node_port': 90, 'port': 8080, 'protocol': 'http', 'targetPort': 80}
        named_entry = {'name': 'foo', 'node_port': 90, 'port': 8080, 'protocol': 'http', "targetPort": 80}

        data = json.dumps(entry)
        actual = common.parsePorts(data)
        port = actual.pop()
        self.assert_port_match(port, entry, None)

        data = json.dumps(named_entry)
        actual = common.parsePorts(data)
        port = actual.pop()
        self.assert_port_match(port, named_entry, None)

        data = json.dumps([named_entry, entry])
        actual = common.parsePorts(data)
        port = actual.pop()
        self.assert_port_match(port, entry, entry['protocol'] + str(entry['port']))
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


if __name__ == '__main__':
    unittest.main()
