"""
Unit tests for pods-resource-model.py functions.
"""

import importlib
import os
import shlex
import sys
import unittest
from unittest.mock import MagicMock, patch

from kubernetes.client.rest import ApiException


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
        'nodename_format': os.environ.get('RD_CONFIG_NODENAME_FORMAT'),
    }
    data = _nodeCollectData(pod, container, config)
    # main() renders the nodename once the index is final; mirror that here so
    # direct-call tests exercise the same naming path.
    data['nodename'] = pods_resource_model.render_nodename(data, config)
    return data


# The resource model parses raw API JSON into plain dicts (camelCase keys), so
# fixtures build dicts that mirror the Kubernetes pod JSON rather than client objects.
def make_container(name='app', image='nginx:latest'):
    return {'name': name, 'image': image}


def make_pod(name='my-pod', namespace='default', pod_ip='10.0.0.1',
             host_ip='192.168.1.1', phase='Running', labels=None,
             container_statuses=None, conditions=None, owner_references=None):
    status = {'phase': phase, 'podIP': pod_ip, 'hostIP': host_ip}
    if container_statuses is not None:
        status['containerStatuses'] = container_statuses
    if conditions is not None:
        status['conditions'] = conditions
    metadata = {'name': name, 'namespace': namespace, 'labels': labels}
    if owner_references is not None:
        metadata['ownerReferences'] = owner_references
    return {
        'metadata': metadata,
        'spec': {'containers': []},
        'status': status,
    }


def make_deployment_pod(name, suffix, hash_='7f4b8bbfc6', container_statuses=None,
                        namespace='default'):
    # A pod owned by a Deployment's ReplicaSet, named <name>-<hash>-<suffix>.
    return make_pod(
        name=f'{name}-{hash_}-{suffix}',
        namespace=namespace,
        labels={'pod-template-hash': hash_},
        owner_references=[{'kind': 'ReplicaSet', 'name': f'{name}-{hash_}', 'controller': True}],
        container_statuses=container_statuses,
    )


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

    def test_running_pod_with_unparseable_started_at(self):
        # A malformed/unexpected startedAt value should not blow up node
        # collection for the whole pod; it should just leave started_at unset.
        container = make_container()
        cs = make_container_status(name='app', running=True, started_at='not-a-timestamp')
        pod = make_pod(container_statuses=[cs])

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('running', data['default:status'])
        self.assertIsNone(data['default:started_at'])

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

    def test_custom_mapping_from_label(self):
        # A label key cannot be written as a ${...} token when it contains
        # characters the operator would rather not repeat; a mapping gives it a
        # short alias usable anywhere a node attribute is.
        container = make_container()
        pod = make_pod(labels={'app.kubernetes.io/service': 'checkout'},
                       container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes',
                               'service.selector=labels:app.kubernetes.io/service', False)
        self.assertEqual('checkout', data['service'])

    def test_custom_mapping_keeps_an_empty_label_value(self):
        # Kubernetes label values may be empty. A truth test on the resolved
        # value dropped the mapping even though its source exists.
        container = make_container()
        pod = make_pod(labels={'app.kubernetes.io/component': ''},
                       container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes',
                               'component.selector=labels:app.kubernetes.io/component', False)
        self.assertIn('component', data)
        self.assertEqual('', data['component'])

    def test_custom_mapping_unknown_source_is_skipped(self):
        container = make_container()
        pod = make_pod(container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes',
                               'nope.selector=labels:does-not-exist', False)
        self.assertNotIn('nope', data)

    def test_tag_selector_missing_attribute_omits_the_tag(self):
        # A label only some pods carry must not take the whole node source down:
        # indexing raised KeyError out of main() and no nodes were emitted at all.
        container = make_container()
        pod = make_pod(labels={'other': 'x'}, container_statuses=None)

        data = nodeCollectData(pod, container, '',
                               'kubernetes,tag.selector=labels:absent', None, False)
        self.assertEqual('pods,kubernetes', data['tags'])

    def test_tag_selector_unset_attribute_omits_the_tag(self):
        # default:status_message is None on a healthy pod, so this selector
        # failed on an entirely normal cluster.
        container = make_container()
        pod = make_pod(container_statuses=None)

        data = nodeCollectData(pod, container, '',
                               'kubernetes,tag.selector=default:status_message', None, False)
        self.assertEqual('pods,kubernetes', data['tags'])

    def test_tag_selector_non_string_attribute(self):
        # terminated is a bool; joining it raised TypeError.
        container = make_container()
        pod = make_pod(container_statuses=None)

        data = nodeCollectData(pod, container, '',
                               'kubernetes,tag.selector=terminated', None, False)
        self.assertEqual('pods,kubernetes,False', data['tags'])

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

    def test_workload_strips_pod_template_hash(self):
        container = make_container(name='web')
        pod = make_deployment_pod('my-app', '2q2hd', container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('my-app', data['default:workload'])
        # full pod name is still available for traceability
        self.assertEqual('my-app-7f4b8bbfc6-2q2hd', data['default:name'])

    def test_workload_falls_back_to_pod_name(self):
        container = make_container(name='web')
        pod = make_pod(name='lonely-pod', container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('lonely-pod', data['default:workload'])

    def test_workload_prefers_controller_owner(self):
        # A non-controller owner listed first must be ignored in favor of the controller.
        container = make_container(name='web')
        pod = make_pod(
            name='my-app-7f4b8bbfc6-2q2hd',
            labels={'pod-template-hash': '7f4b8bbfc6'},
            owner_references=[
                {'kind': 'Foo', 'name': 'some-other-owner'},
                {'kind': 'ReplicaSet', 'name': 'my-app-7f4b8bbfc6', 'controller': True},
            ],
            container_statuses=None,
        )

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('my-app', data['default:workload'])

    def test_nodename_format_default(self):
        container = make_container(name='web')
        pod = make_pod(name='my-pod', container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('my-pod-web', data['nodename'])

    def test_nodename_format_template_with_labels(self):
        os.environ['RD_CONFIG_NODENAME_FORMAT'] = (
            '${labels:site}-${labels:deployment_group}-${default:name}-${default:container_name}'
        )
        container = make_container(name='web')
        pod = make_pod(name='my-pod',
                       labels={'site': 'us-east', 'deployment_group': 'blue'},
                       container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('us-east-blue-my-pod-web', data['nodename'])

    def test_nodename_format_missing_attribute_is_blank(self):
        os.environ['RD_CONFIG_NODENAME_FORMAT'] = '${labels:site}-${default:name}'
        container = make_container(name='web')
        pod = make_pod(name='my-pod', labels=None, container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('-my-pod', data['nodename'])

    def test_nodename_workload_and_index(self):
        os.environ['RD_CONFIG_NODENAME_FORMAT'] = '${default:workload}-${index}'
        container = make_container(name='web')
        pod = make_deployment_pod('my-app', '2q2hd', container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('my-app-1', data['nodename'])

    def test_nodename_unset_attribute_renders_blank_not_none(self):
        # An unscheduled pod has no podIP. Rendering that as "None" would put the
        # word in the node name and give every pending pod the same one.
        os.environ['RD_CONFIG_NODENAME_FORMAT'] = '${default:name}-${default:pod_id}'
        container = make_container(name='web')
        pod = make_pod(name='my-pod', pod_ip=None, container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes', None, False)
        self.assertEqual('my-pod-', data['nodename'])

    def test_explicit_nodename_mapping_wins_over_the_template(self):
        # nodename.selector=default:name is the first example in the README, so
        # the template must not silently rename the nodes of an existing job.
        os.environ['RD_CONFIG_NODENAME_FORMAT'] = '${default:workload}-${index}'
        container = make_container(name='web')
        pod = make_deployment_pod('my-app', '2q2hd', container_statuses=None)

        data = nodeCollectData(pod, container, '', 'kubernetes',
                               'nodename.selector=default:name', False)
        self.assertEqual('my-app-7f4b8bbfc6-2q2hd', data['nodename'])

    def test_explicit_nodename_default_wins_over_the_template(self):
        os.environ['RD_CONFIG_NODENAME_FORMAT'] = '${default:workload}-${index}'
        container = make_container(name='web')
        pod = make_deployment_pod('my-app', '2q2hd', container_statuses=None)

        data = nodeCollectData(pod, container, 'nodename=fixed-name', 'kubernetes',
                               None, False)
        self.assertEqual('fixed-name', data['nodename'])


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
    def test_main_no_trailing_empty_tag_when_tags_unset(self, mock_connect, mock_collect):
        # RD_CONFIG_TAGS intentionally left unset: tags.split(',') on the ''
        # default would otherwise produce [''], showing up as a trailing
        # empty tag ("pods,") in the output.
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''

        container = make_container()
        pod = make_pod(name='pod-a', container_statuses=None)

        mock_collect.return_value = self._make_pod_list([(pod, [container])])

        with patch('builtins.print') as mock_print:
            main()

        import json
        output = mock_print.call_args[0][0]
        nodes = json.loads(output)
        self.assertEqual('pods', nodes[0]['tags'])

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_keeps_running_pods_when_emoticons_are_enabled(self, mock_connect, mock_collect):
        # With emoticons the status attribute is "<emoticon> running", which
        # the running filter compared with "running" and so dropped every pod.
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''
        os.environ['RD_CONFIG_RUNNING'] = 'true'
        os.environ['RD_CONFIG_EMOTICON'] = 'true'

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
        self.assertEqual(['pod-a-app'], [n['nodename'] for n in nodes])
        self.assertIn(u'\U0001f44d', nodes[0]['status'])

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

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_logs_and_exits_on_api_exception(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''

        api_exception = ApiException(status=401, reason='Unauthorized')
        api_exception.body = 'Invalid bearer token'
        mock_collect.side_effect = api_exception

        with self.assertRaises(SystemExit) as cm, \
                self.assertLogs('kubernetes-model-source', level='ERROR') as log_ctx:
            main()

        self.assertEqual(cm.exception.code, 1)
        joined_logs = '\n'.join(log_ctx.output)
        self.assertIn('401', joined_logs)
        self.assertIn('Unauthorized', joined_logs)
        self.assertIn('Invalid bearer token', joined_logs)

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_indexes_containers_within_parent(self, mock_connect, mock_collect):
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''

        c1 = make_container(name='app')
        c2 = make_container(name='sidecar')
        statuses = [make_container_status(name='app', running=True),
                    make_container_status(name='sidecar', running=True)]

        # Pods are grouped by workload (owner minus pod-template-hash), so each
        # container name gets its own sequence within a Deployment.
        pods = [make_deployment_pod('rs', 'aaaaa', container_statuses=statuses),
                make_deployment_pod('rs', 'bbbbb', container_statuses=statuses),
                make_deployment_pod('other', 'ccccc', container_statuses=statuses)]

        mock_collect.return_value = self._make_pod_list([(p, [c1, c2]) for p in pods])

        with patch('builtins.print') as mock_print:
            main()

        import json
        indexes = {n['nodename']: n['index'] for n in json.loads(mock_print.call_args[0][0])}
        self.assertEqual(indexes['rs-7f4b8bbfc6-aaaaa-app'], 1)
        self.assertEqual(indexes['rs-7f4b8bbfc6-aaaaa-sidecar'], 1)
        self.assertEqual(indexes['rs-7f4b8bbfc6-bbbbb-app'], 2)
        self.assertEqual(indexes['rs-7f4b8bbfc6-bbbbb-sidecar'], 2)
        self.assertEqual(indexes['other-7f4b8bbfc6-ccccc-app'], 1)

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_replicas_indexed_by_workload(self, mock_connect, mock_collect):
        # Three replicas of one Deployment get unique, hash-free numbered names.
        # The template carries the namespace because the index is counted per
        # namespace: without it, the same workload name in two namespaces would
        # produce the same node name on an all-namespaces scan.
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''
        os.environ['RD_CONFIG_NODENAME_FORMAT'] = (
            '${default:namespace}-${default:workload}-${index}')

        container = make_container(name='app')
        cs = make_container_status(name='app', running=True)
        mock_collect.return_value = self._make_pod_list([
            (make_deployment_pod('my-app', suffix, container_statuses=[cs]), [container])
            for suffix in ('2q2hd', 'h7m4k', 'z6ztb')
        ])

        with patch('builtins.print') as mock_print:
            main()

        import json
        nodes = json.loads(mock_print.call_args[0][0])
        self.assertEqual(['default-my-app-1', 'default-my-app-2', 'default-my-app-3'],
                         [n['nodename'] for n in nodes])

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_numbers_only_the_pods_it_emits(self, mock_connect, mock_collect):
        # A filtered-out pod must not consume an index, or a workload whose first
        # pod is Terminated emits nodes numbered 2 and 3 and "index == 1" -- the
        # documented way to target a single replica -- matches nothing.
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''

        container = make_container(name='app')
        gone = make_container_status(name='app', running=False, terminated=True)
        live = make_container_status(name='app', running=True)
        mock_collect.return_value = self._make_pod_list([
            (make_deployment_pod('my-app', '2q2hd', container_statuses=[gone]), [container]),
            (make_deployment_pod('my-app', 'h7m4k', container_statuses=[live]), [container]),
            (make_deployment_pod('my-app', 'z6ztb', container_statuses=[live]), [container]),
        ])

        with patch('builtins.print') as mock_print:
            main()

        import json
        nodes = json.loads(mock_print.call_args[0][0])
        self.assertEqual([1, 2], sorted(n['index'] for n in nodes))

    @patch.object(pods_resource_model, 'collect_pods_from_api')
    @patch.object(pods_resource_model.common, 'connect')
    def test_main_one_per_workload(self, mock_connect, mock_collect):
        # With the toggle on, three replicas collapse to a single node, while the
        # specific pod name stays available as default:name for kubectl traceability.
        os.environ['RD_CONFIG_TAGS'] = 'kubernetes'
        os.environ['RD_CONFIG_ATTRIBUTES'] = ''
        os.environ['RD_CONFIG_ONE_PER_WORKLOAD'] = 'true'

        container = make_container(name='app')
        cs = make_container_status(name='app', running=True)
        mock_collect.return_value = self._make_pod_list([
            (make_deployment_pod('my-app', suffix, container_statuses=[cs]), [container])
            for suffix in ('2q2hd', 'h7m4k', 'z6ztb')
        ])

        with patch('builtins.print') as mock_print:
            main()

        import json
        nodes = json.loads(mock_print.call_args[0][0])
        self.assertEqual(1, len(nodes))
        self.assertEqual('my-app', nodes[0]['default:workload'])
        self.assertEqual('my-app-7f4b8bbfc6-2q2hd', nodes[0]['default:name'])
        self.assertEqual('default', nodes[0]['default:namespace'])
        self.assertEqual('app', nodes[0]['default:container_name'])


if __name__ == '__main__':
    unittest.main()
