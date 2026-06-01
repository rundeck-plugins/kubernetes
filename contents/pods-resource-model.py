#!/usr/bin/env python
import datetime
import logging
import sys
import os
import common
import json
import shlex

from kubernetes import client


logging.basicConfig(stream=sys.stderr,
                    level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s'
                    )
log = logging.getLogger('kubernetes-model-source')


def format_started_at(started):
    # With _preload_content=False the API's startedAt arrives as an RFC 3339 string
    # (e.g. "2024-06-15T10:30:00Z") rather than a datetime. Reformat it to the
    # "YYYY-MM-DD HH:MM:SS" shape this attribute has always produced.
    if not started:
        return None
    parsed = datetime.datetime.fromisoformat(started.replace('Z', '+00:00'))
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def nodeCollectData(pod, container, config):
    # config carries the per-run options parsed once in main() (tags, mappings,
    # defaults, emoticon flag, config file) so they are not re-parsed for every node.
    tags = config['tags']
    boEmoticon = config['emoticon']

    metadata = pod['metadata']
    pod_status = pod['status']
    container_name = container['name']
    pod_labels = metadata.get('labels')

    status = pod_status.get('phase')
    statusMessage = None
    startedAt = None

    terminated = False
    container_id = None

    container_statuses = pod_status.get('containerStatuses')
    if container_statuses:

        log.info("------")
        log.info("container-name:" + container_name)

        for statuses in container_statuses:
            log.info("pod-container-name:" + statuses['name'])

            if container_name == statuses['name']:
                state = statuses.get('state') or {}
                if state.get('running') is not None:
                    status = "running"
                    startedAt = format_started_at(state['running'].get('startedAt'))

                if state.get('waiting') is not None:
                    status = "waiting"

                if state.get('terminated') is not None:
                    terminated = True
                    status = "terminated"

                container_id = statuses.get('containerID')

    if terminated is False and pod_status.get('conditions') is not None:
        for info in pod_status['conditions']:
            if info.get('status') == 'False':
                status = info.get('reason')
                statusMessage = info.get('message')

    labels = []

    if pod_labels:
        for keys, values in pod_labels.items():
            labels.append(keys + ":" + values)

    default_settings = {
        # kubernetes:config_file attribute are kept to avoid breaking existing k8s jobs depend on this configuration-override hack
        # This is just a temporary workaround solution and should be replaced by a layered configuration-override mechanism.
        'kubernetes:config_file': config['config_file'],
        'default:pod_id': pod_status.get('podIP'),
        'default:host_id': pod_status.get('hostIP'),
        'default:started_at': startedAt,
        'default:name': metadata['name'],
        'default:labels': ','.join(labels),
        'default:namespace': metadata['namespace'],
        'default:image': container.get('image'),
        'default:status': status,
        'default:status_message': statusMessage,
        'default:container_id': container_id,
        'default:container_name': container_name
    }

    custom_attributes = {}

    # custom mapping attributes
    if config['mappings']:
        log.debug('Mapping: %s', config['mappings'])

        for mapping in config['mappings']:
            mapping_array = dict(s.split('=', 1) for s in mapping.split())

            for key, value in mapping_array.items():
                if ".selector" in key:
                    attribute = key.replace(".selector", "")
                    custom_attribute = None
                    # take the values from default
                    if "default:" in value:
                        custom_attribute = default_settings[value]

                    if custom_attribute:
                        custom_attributes[attribute] = custom_attribute

        log.debug('Custom Attributes: %s', custom_attributes)

    # rundeck attributes
    data = default_settings
    data['nodename'] = default_settings['default:name']+"-"+container_name
    data['hostname'] = default_settings['default:pod_id']
    data['terminated'] = terminated

    # Add labels as its own map of node attributes.
    if pod_labels is not None:
        for key, value in pod_labels.items():
            data['labels:' + key] = value

    emoticon = ""
    if default_settings['default:status'] == "running":
        emoticon = u'\U0001f44d'
    if default_settings['default:status'] == "terminated":
        emoticon = u'\U00002705'
    if default_settings['default:status'] == "ContainersNotReady":
        emoticon = u'\U0000274c'
    if default_settings['default:status'] == "waiting":
        emoticon = u'\U0000274c'

    if boEmoticon:
        data['status'] = emoticon + " " + default_settings['default:status']
        desc = emoticon + " " + default_settings['default:status']
    else:
        data['status'] = default_settings['default:status']
        desc = default_settings['default:status']

    if default_settings['default:status_message']:
        desc = desc + "(" + default_settings['default:status_message'] + ")"

    data['description'] = desc

    final_tags = ["pods"]

    for tag in tags:
        if "tag.selector=" in tag:
            custom_tag = data[tag.replace("tag.selector=", "")]
            final_tags.append(custom_tag)
        else:
            final_tags.append(tag)

    data['tags'] = ','.join(final_tags)

    if custom_attributes:
        data = dict(list(data.items()) + list(custom_attributes.items()))

    data.update(config['defaults'])

    return data


def collect_pods_from_api(namespace_filter, label_selector, field_selector, use_cache=False):
    v1 = client.CoreV1Api()

    log.debug(label_selector)
    log.debug(field_selector)

    # _preload_content=False returns the raw HTTP response so the JSON can be parsed
    # directly into plain dicts. This skips the client's per-object model
    # deserialization, which dominates wall-clock time on large pod lists.
    kwargs = {'watch': False, '_preload_content': False}

    # resource_version='0' lets the apiserver serve the list from its in-memory watch
    # cache instead of a quorum read from etcd: much faster on large clusters and
    # lighter on the control plane, at the cost of possibly-stale data. Opt-in.
    if use_cache:
        kwargs['resource_version'] = '0'

    if label_selector:
        kwargs['label_selector'] = label_selector
    if field_selector:
        kwargs['field_selector'] = field_selector

    if namespace_filter:
        resp = v1.list_namespaced_pod(namespace=namespace_filter, **kwargs)
    else:
        resp = v1.list_pod_for_all_namespaces(**kwargs)

    return json.loads(resp.data).get('items', [])


def main():
    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    common.connect()

    tags = os.environ.get('RD_CONFIG_TAGS', '')
    mappingList = os.environ.get('RD_CONFIG_MAPPING')
    defaults = os.environ.get('RD_CONFIG_ATTRIBUTES')

    running = False
    if os.environ.get('RD_CONFIG_RUNNING') == 'true':
        running = True

    boEmoticon = False
    if os.environ.get('RD_CONFIG_EMOTICON') == 'true':
        boEmoticon = True

    use_cache = False
    if os.environ.get('RD_CONFIG_USE_CACHE') == 'true':
        use_cache = True

    field_selector = None
    if os.environ.get('RD_CONFIG_FIELD_SELECTOR'):
        field_selector = os.environ.get('RD_CONFIG_FIELD_SELECTOR')

    namespace_filter = None
    if os.environ.get('RD_CONFIG_NAMESPACE_FILTER'):
        namespace_filter = os.environ.get('RD_CONFIG_NAMESPACE_FILTER')

    # Opt-in: exclude namespaces server-side via the field selector. Defaults to
    # empty (no exclusion, no behavior change). Only applied to all-namespace
    # queries; a specific Namespace already scopes the result.
    exclude_namespaces = os.environ.get('RD_CONFIG_EXCLUDE_NAMESPACES', '')
    if not namespace_filter and exclude_namespaces:
        exclusions = ['metadata.namespace!=' + ns.strip()
                      for ns in exclude_namespaces.split(',') if ns.strip()]
        if exclusions:
            field_selector = ','.join([field_selector] + exclusions) if field_selector else ','.join(exclusions)

    label_selector = None

    if os.environ.get('RD_CONFIG_LABEL_SELECTOR'):
        label_selector = os.environ.get('RD_CONFIG_LABEL_SELECTOR')

    # Parse the per-node options once here rather than re-parsing the same config
    # strings inside nodeCollectData for every container.
    config = {
        'tags': tags.split(','),
        'mappings': mappingList.split(',') if mappingList else [],
        'defaults': dict(token.split('=') for token in shlex.split(defaults or '')),
        'emoticon': boEmoticon,
        'config_file': os.environ.get('RD_CONFIG_CONFIG_FILE'),
    }

    node_set = []

    ret = collect_pods_from_api(namespace_filter, label_selector, field_selector, use_cache=use_cache)

    for i in ret:
        for container in i['spec']['containers']:
            log.debug("%s\t%s\t%s\t%s",
                      i['status'].get('podIP'),
                      i['metadata']['namespace'],
                      i['metadata']['name'],
                      container['name'])

            node_data = nodeCollectData(i, container, config)

            if running is False:
                if node_data["terminated"] is False:
                    node_set.append(node_data)

            if running is True:
                if node_data["status"].lower() == "running":
                    node_set.append(node_data)

    print(json.dumps(node_set, sort_keys=True))


if __name__ == '__main__':
    main()
