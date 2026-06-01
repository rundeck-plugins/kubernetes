"""
Unit tests for pods-resource-model.py functions.
"""

import importlib
import os
import shlex
import sys
import unittest
from unittest.mock import MagicMock, patch


# pods-resource-model.py has a hyphenated name, so use importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pods_resource_model = importlib.import_module('pods-resource-model')
collect_pods_from_api = pods_resource_model.collect_pods_from_api
main = pods_resource_model.main

# nodeCollectData now takes a config dict (parsed once in main) instead of flat config
# strings. Adapt the flat-argument call shape these tests use to the new signature.
_nodeCollectData = pods_resource_model.nodeCollectData


def nodeCollectData(pod, container, defaults, taglist, mappingList, boEmoticon):
    config = {
        'tags': taglist.split(',') if taglist else [],
        'mappings': mappingList.split(',') if mappingList else [],
        'defaults': dict(token.split('=') for token in shlex.split(defaults or '')),
        'emoticon': boEmoticon,
        'config_file': os.environ.get('RD_CONFIG_CONFIG_FILE'),
    }
    return _nodeCollectData(pod, container, config)


# The resource model parses raw API JSON into plain dicts (camelCase keys), so
# fixtures build dicts that mirror the Kubernetes pod JSON rather than client objects.
def make_container(name='app', image='nginx:latest'):
    return {'name': name, 'image': image}


def make_pod(name='my-pod', namespace='default', pod_ip='10.0.0.1',
             host_ip='192.168.1.1', phase='Running', labels=None,
             container_statuses=None, conditions=None):
    status = {'phase': phase, 'podIP': pod_ip, 'hostIP': host_ip}
    if container_statuses is not None:
        status['containerStatuses'] = container_statuses
    if conditions is not None:
        status['conditions'] = conditions
    return {
        'metadata': {'name': name, 'namespace': namespace, 'labels': labels},
        'spec': {'containers': []},
        'status': status,
    }


def make_container_status(name='app', running=True, started_at=None,
                          waiting=False, terminated=False, container_id='docker://abc123'):
    state = {
        'running': {'startedAt': started_at} if running else None,
        'waiting': {} if waiting else None,
        'terminated': {} if terminated else None,
    }
    return {'name': name, 'containerID': container_id, 'state': state}


class TestNodeCollectData(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    def test_basic_running_pod(self):
        started = '2024-06-15T10:30:00Z'
        container = make_container()
        cs = make_container_status(name='app', running=True, started_at=started)
        pod = make_pod(container_statuses=[cs])

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)

        self.assertEqual('my-pod-app', data['nodename'])
        self.assertEqual('10.0.0.1', data['hostname'])
        self.assertEqual('running', data['default:status'])
        self.assertEqual('2024-06-15 10:30:00', data['default:started_at'])
        self.assertEqual('docker://abc123', data['default:container_id'])
        self.assertEqual('app', data['default:container_name'])
        self.assertEqual('nginx:latest', data['default:image'])
        self.assertFalse(data['terminated'])
        self.assertIn('pods', data['tags'])

    def test_waiting_pod(self):
        container = make_container()
        cs = make_container_status(name='app', running=False, waiting=True)
        pod = make_pod(container_statuses=[cs])

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('waiting', data['default:status'])

    def test_terminated_pod(self):
        container = make_container()
        cs = make_container_status(name='app', running=False, terminated=True)
        pod = make_pod(container_statuses=[cs])

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('terminated', data['default:status'])
        self.assertTrue(data['terminated'])

    def test_no_container_statuses(self):
        container = make_container()
        pod = make_pod(phase='Pending', container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('Pending', data['default:status'])
        self.assertFalse(data['terminated'])

    def test_conditions_not_ready(self):
        container = make_container()
        condition = {
            'status': 'False',
            'reason': 'ContainersNotReady',
            'message': 'containers not ready',
        }
        pod = make_pod(container_statuses=None, conditions=[condition])

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('ContainersNotReady', data['default:status'])
        self.assertEqual('containers not ready', data['default:status_message'])

    def test_labels_added(self):
        container = make_container()
        labels = {'app': 'web', 'env': 'prod'}
        pod = make_pod(labels=labels, container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('web', data['labels:app'])
        self.assertEqual('prod', data['labels:env'])
        self.assertIn('app:web', data['default:labels'])
        self.assertIn('env:prod', data['default:labels'])

    def test_emoticon_enabled(self):
        container = make_container()
        cs = make_container_status(name='app', running=True)
        pod = make_pod(container_statuses=[cs])

        data = nodeCollectData(pod, container, '', 'kubernetes', None, True)
        self.assertIn(u'\U0001f44d', data['status'])
        self.assertIn(u'\U0001f44d', data['description'])

    def test_emoticon_disabled(self):
        container = make_container()
        cs = make_container_status(name='app', running=True)
        pod = make_pod(container_statuses=[cs])

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('running', data['status'])

    def test_custom_tags(self):
        container = make_container()
        cs = make_container_status(name='app', running=True)
        pod = make_pod(container_statuses=[cs])

        data = nodeCollectData(pod, container, '', 'tag.selector=default:image,mytag', None, False)
        self.assertIn('pods', data['tags'])
        self.assertIn('nginx:latest', data['tags'])
        self.assertIn('mytag', data['tags'])

    def test_defaults_applied(self):
        container = make_container()
        pod = make_pod(container_statuses=None)

        data = nodeCollectData(pod, container, 'username=root osFamily=unix', 'kubernetes', None, False)
        self.assertEqual('root', data['username'])
        self.assertEqual('unix', data['osFamily'])

    def test_custom_mapping(self):
        container = make_container()
        cs = make_container_status(name='app', running=True)
        pod = make_pod(container_statuses=[cs])

        data = nodeCollectData(pod, container, '', 'kubernetes',
                               'hostname.selector=default:pod_id', False)
        self.assertEqual('10.0.0.1', data['hostname'])

    def test_status_message_in_description(self):
        container = make_container()
        condition = {
            'status': 'False',
            'reason': 'ContainersNotReady',
            'message': 'waiting for readiness',
        }
        pod = make_pod(container_statuses=None, conditions=[condition])

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertIn('waiting for readiness', data['description'])

    def test_config_file_env(self):
        os.environ['RD_CONFIG_CONFIG_FILE'] = '/etc/kube/config'
        container = make_container()
        pod = make_pod(container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('/etc/kube/config', data['kubernetes:config_file'])


class TestCollectPodsFromApi(unittest.TestCase):

    @staticmethod
    def _resp(payload='{"items": "result"}'):
        # collect_pods_from_api requests the raw response (_preload_content=False)
        # and parses resp.data as JSON, returning the "items" list.
        resp = MagicMock()
        resp.data = payload
        return resp

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_all_namespaces_both_selectors(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = self._resp()

        ret = collect_pods_from_api(None, 'app=web', 'status.phase=Running')
        mock_api.list_pod_for_all_namespaces.assert_called_once_with(
            watch=False,
            _preload_content=False,
            field_selector='status.phase=Running',
            label_selector='app=web',
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_all_namespaces_field_selector_only(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = self._resp()

        ret = collect_pods_from_api(None, None, 'status.phase=Running')
        mock_api.list_pod_for_all_namespaces.assert_called_once_with(
            watch=False,
            _preload_content=False,
            field_selector='status.phase=Running',
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_all_namespaces_label_selector_only(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = self._resp()

        ret = collect_pods_from_api(None, 'app=web', None)
        mock_api.list_pod_for_all_namespaces.assert_called_once_with(
            watch=False,
            _preload_content=False,
            label_selector='app=web',
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_all_namespaces_no_selectors(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = self._resp()

        ret = collect_pods_from_api(None, None, None)
        mock_api.list_pod_for_all_namespaces.assert_called_once_with(
            watch=False,
            _preload_content=False,
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_namespaced(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_namespaced_pod.return_value = self._resp()

        ret = collect_pods_from_api('prod', 'app=web', 'status.phase=Running')
        mock_api.list_namespaced_pod.assert_called_once_with(
            namespace='prod',
            watch=False,
            _preload_content=False,
            label_selector='app=web',
            field_selector='status.phase=Running',
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_namespaced_no_selectors(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_namespaced_pod.return_value = self._resp()

        ret = collect_pods_from_api('default', None, None)
        mock_api.list_namespaced_pod.assert_called_once_with(
            namespace='default',
            watch=False,
            _preload_content=False,
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_use_cache_sets_resource_version(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = self._resp()

        collect_pods_from_api(None, None, None, use_cache=True)
        mock_api.list_pod_for_all_namespaces.assert_called_once_with(
            watch=False,
            _preload_content=False,
            resource_version='0',
        )

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_no_cache_omits_resource_version(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = self._resp()

        collect_pods_from_api(None, None, None)
        _, kwargs = mock_api.list_pod_for_all_namespaces.call_args
        self.assertNotIn('resource_version', kwargs)


class TestMain(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    def _make_pod_list(self, pods):
        # collect_pods_from_api returns a plain list of pod dicts.
        items = []
        for pod, containers in pods:
            pod['spec']['containers'] = containers
            items.append(pod)
        return items

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_filters_terminated_when_not_running(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''

        container = make_container()
        cs_running = make_container_status(name='app', running=True)
        cs_terminated = make_container_status(name='app', running=False, terminated=True)

        pod_running = make_pod(name='pod-a', container_statuses=[cs_running])
        pod_terminated = make_pod(name='pod-b', container_statuses=[cs_terminated])

        mock_collect.return_value = self._make_pod_list([
            (pod_running, [container]),
            (pod_terminated, [container]),
        ])

        with patch('builtins.print') as mock_print:
            main()

        import json
        output = mock_print.call_args[0][0]
        nodes = json.loads(output)
        node_names = [n['nodename'] for n in nodes]
        self.assertIn('pod-a-app', node_names)
        self.assertNotIn('pod-b-app', node_names)

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_filters_only_running_when_running_true(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''
        os.environ['RD_CONFIG_RUNNING'] = 'true'

        container = make_container()
        cs_running = make_container_status(name='app', running=True)
        cs_waiting = make_container_status(name='app', running=False, waiting=True)

        pod_running = make_pod(name='pod-a', container_statuses=[cs_running])
        pod_waiting = make_pod(name='pod-b', container_statuses=[cs_waiting])

        mock_collect.return_value = self._make_pod_list([
            (pod_running, [container]),
            (pod_waiting, [container]),
        ])

        with patch('builtins.print') as mock_print:
            main()

        import json
        output = mock_print.call_args[0][0]
        nodes = json.loads(output)
        node_names = [n['nodename'] for n in nodes]
        self.assertIn('pod-a-app', node_names)
        self.assertNotIn('pod-b-app', node_names)

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_passes_env_to_collect(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''
        os.environ['RD_CONFIG_NAMESPACE_FILTER'] = 'prod'
        os.environ['RD_CONFIG_LABEL_SELECTOR'] = 'app=web'
        os.environ['RD_CONFIG_FIELD_SELECTOR'] = 'status.phase=Running'

        mock_collect.return_value = []

        with patch('builtins.print'):
            main()

        mock_collect.assert_called_once_with('prod', 'app=web', 'status.phase=Running', use_cache=False)

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_use_cache_flag(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''
        os.environ['RD_CONFIG_USE_CACHE'] = 'true'

        mock_collect.return_value = []

        with patch('builtins.print'):
            main()

        _, kwargs = mock_collect.call_args
        self.assertTrue(kwargs['use_cache'])

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_excludes_namespaces_when_configured(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''
        os.environ['RD_CONFIG_EXCLUDE_NAMESPACES'] = 'kube-system, kube-public'

        mock_collect.return_value = []

        with patch('builtins.print'):
            main()

        _, _, field_selector = mock_collect.call_args[0]
        self.assertIn('metadata.namespace!=kube-system', field_selector)
        self.assertIn('metadata.namespace!=kube-public', field_selector)

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_no_exclusion_by_default(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''

        mock_collect.return_value = []

        with patch('builtins.print'):
            main()

        # No RD_CONFIG_EXCLUDE_NAMESPACES set -> field_selector stays None (no change).
        _, _, field_selector = mock_collect.call_args[0]
        self.assertIsNone(field_selector)

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_emoticon_flag(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''
        os.environ['RD_CONFIG_EMOTICON'] = 'true'

        container = make_container()
        cs = make_container_status(name='app', running=True)
        pod = make_pod(name='pod-a', container_statuses=[cs])

        mock_collect.return_value = self._make_pod_list([(pod, [container])])

        with patch('builtins.print') as mock_print:
            main()

        import json
        output = mock_print.call_args[0][0]
        nodes = json.loads(output)
        self.assertIn(u'\U0001f44d', nodes[0]['status'])

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_multiple_containers(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''

        c1 = make_container(name='app', image='nginx')
        c2 = make_container(name='sidecar', image='envoy')
        cs1 = make_container_status(name='app', running=True)
        cs2 = make_container_status(name='sidecar', running=True)
        pod = make_pod(name='pod-a', container_statuses=[cs1, cs2])

        mock_collect.return_value = self._make_pod_list([(pod, [c1, c2])])

        with patch('builtins.print') as mock_print:
            main()

        import json
        output = mock_print.call_args[0][0]
        nodes = json.loads(output)
        node_names = [n['nodename'] for n in nodes]
        self.assertIn('pod-a-app', node_names)
        self.assertIn('pod-a-sidecar', node_names)

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_empty_pod_list(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''

        mock_collect.return_value = []

        with patch('builtins.print') as mock_print:
            main()

        import json
        output = mock_print.call_args[0][0]
        self.assertEqual([], json.loads(output))


if __name__ == '__main__':
    unittest.main()
