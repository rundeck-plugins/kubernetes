"""
Unit tests for pods-resource-model.py functions.
"""

import datetime
import importlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


# pods-resource-model.py has a hyphenated name, so use importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pods_resource_model = importlib.import_module('pods-resource-model')
nodeCollectData = pods_resource_model.nodeCollectData
collect_pods_from_api = pods_resource_model.collect_pods_from_api
main = pods_resource_model.main

def make_container(name='app', image='nginx:latest'):
    container = MagicMock()
    container.name = name
    container.image = image
    return container


def make_pod(name='my-pod', namespace='default', pod_ip='10.0.0.1',
             host_ip='192.168.1.1', phase='Running', labels=None,
             container_statuses=None, conditions=None):
    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.namespace = namespace
    pod.metadata.labels = labels
    pod.status.pod_ip = pod_ip
    pod.status.host_ip = host_ip
    pod.status.phase = phase
    pod.status.container_statuses = container_statuses
    pod.status.conditions = conditions
    return pod


def make_container_status(name='app', running=True, started_at=None,
                          waiting=False, terminated=False, container_id='docker://abc123'):
    status = MagicMock()
    status.name = name
    status.container_id = container_id

    if running:
        status.state.running = MagicMock()
        status.state.running.started_at = started_at
    else:
        status.state.running = None

    if waiting:
        status.state.waiting = MagicMock()
    else:
        status.state.waiting = None

    if terminated:
        status.state.terminated = MagicMock()
    else:
        status.state.terminated = None

    return status


class TestNodeCollectData(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    def test_basic_running_pod(self):
        started = datetime.datetime(2024, 6, 15, 10, 30, 0)
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
        condition = MagicMock()
        condition.status = 'False'
        condition.reason = 'ContainersNotReady'
        condition.message = 'containers not ready'
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
        condition = MagicMock()
        condition.status = 'False'
        condition.reason = 'ContainersNotReady'
        condition.message = 'waiting for readiness'
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

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_all_namespaces_both_selectors(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = 'result'

        ret = collect_pods_from_api(None, 'app=web', 'status.phase=Running')
        mock_api.list_pod_for_all_namespaces.assert_called_once_with(
            watch=False,
            field_selector='status.phase=Running',
            label_selector='app=web',
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_all_namespaces_field_selector_only(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = 'result'

        ret = collect_pods_from_api(None, None, 'status.phase=Running')
        mock_api.list_pod_for_all_namespaces.assert_called_once_with(
            watch=False,
            field_selector='status.phase=Running',
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_all_namespaces_label_selector_only(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = 'result'

        ret = collect_pods_from_api(None, 'app=web', None)
        mock_api.list_pod_for_all_namespaces.assert_called_once_with(
            watch=False,
            label_selector='app=web',
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_all_namespaces_no_selectors(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_pod_for_all_namespaces.return_value = 'result'

        ret = collect_pods_from_api(None, None, None)
        mock_api.list_pod_for_all_namespaces.assert_called_once_with(watch=False)
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_namespaced(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_namespaced_pod.return_value = 'result'

        ret = collect_pods_from_api('prod', 'app=web', 'status.phase=Running')
        mock_api.list_namespaced_pod.assert_called_once_with(
            namespace='prod',
            watch=False,
            label_selector='app=web',
            field_selector='status.phase=Running',
        )
        self.assertEqual('result', ret)

    @patch.object(pods_resource_model.client, 'CoreV1Api')
    def test_namespaced_no_selectors(self, mock_api_class):
        mock_api = mock_api_class.return_value
        mock_api.list_namespaced_pod.return_value = 'result'

        ret = collect_pods_from_api('default', None, None)
        mock_api.list_namespaced_pod.assert_called_once_with(
            namespace='default',
            watch=False,
            label_selector=None,
            field_selector=None,
        )


class TestMain(unittest.TestCase):

    def setUp(self):
        os.environ.clear()

    def _make_pod_list(self, pods):
        ret = MagicMock()
        items = []
        for pod, containers in pods:
            pod.spec.containers = containers
            items.append(pod)
        ret.items = items
        return ret

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

        mock_collect.return_value = MagicMock(items=[])

        with patch('builtins.print'):
            main()

        mock_collect.assert_called_once_with('prod', 'app=web', 'status.phase=Running')

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

        mock_collect.return_value = MagicMock(items=[])

        with patch('builtins.print') as mock_print:
            main()

        import json
        output = mock_print.call_args[0][0]
        self.assertEqual([], json.loads(output))


if __name__ == '__main__':
    unittest.main()