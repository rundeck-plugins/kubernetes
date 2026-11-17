#!/usr/bin/env python
import datetime
import logging
import re
import sys
import os
import common
import json
import shlex

from kubernetes import client
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr,
                    level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s'
                    )
log = logging.getLogger('kubernetes-model-source')


_TEMPLATE_TOKEN = re.compile(r'\$\{([^}]+)\}')

# Default nodename template; reproduces the historical "<pod name>-<container name>".
DEFAULT_NODENAME_FORMAT = '${default:name}-${default:container_name}'


def _render_attribute_template(template, data):
    # Substitute ${attribute} tokens with values from the node data dict, where
    # attribute is any key present in data (e.g. default:name, labels:site,
    # default:container_name). An attribute that is unknown, or known but unset,
    # renders as an empty string -- an unscheduled pod has no podIP, and
    # rendering that as "None" would put the word in the node name and give
    # every such pod the same one.
    def value(match):
        attribute = data.get(match.group(1))
        return '' if attribute is None else str(attribute)

    return _TEMPLATE_TOKEN.sub(value, template)


def render_nodename(data, config):
    # An explicit nodename from Custom Mapping ("nodename.selector=default:name",
    # the first example in the README) or from Default attributes wins. The
    # template is the default naming strategy, not an override of the operator's
    # -- overriding it would silently rename every node of an existing job.
    if data.get('nodename'):
        return data['nodename']

    nodename_format = config.get('nodename_format') or DEFAULT_NODENAME_FORMAT
    return _render_attribute_template(nodename_format, data)


def workload_name(metadata, labels):
    # Best-effort human-friendly workload name: the pod's controlling object, with
    # the Deployment pod-template-hash stripped (e.g. "my-app-7f4b8bbfc6" -> "my-app").
    # StatefulSets, DaemonSets and Jobs carry no such hash, so their owner name is used.
    owner_refs = metadata.get('ownerReferences') or []
    # Prefer controlling owner; fall back to first reference, then pod name.
    owner = next((o for o in owner_refs if o.get('controller')),
                 owner_refs[0] if owner_refs else None)
    name = owner['name'] if owner else metadata['name']
    pod_template_hash = labels.get('pod-template-hash')
    if pod_template_hash and name.endswith('-' + pod_template_hash):
        name = name[:-(len(pod_template_hash) + 1)]
    return name


def format_started_at(started):
    # With _preload_content=False the API's startedAt arrives as an RFC 3339 string
    # (e.g. "2024-06-15T10:30:00Z") rather than a datetime. Reformat it to the
    # "YYYY-MM-DD HH:MM:SS" shape this attribute has always produced.
    if not started:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(started.replace('Z', '+00:00'))
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        log.warning("Could not parse startedAt value %r, leaving it unset", started)
        return None


def nodeCollectData(pod, container, config, index=1):
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
    workload = workload_name(metadata, pod_labels or {})

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
        'default:workload': workload,
        'default:labels': ','.join(labels),
        'default:namespace': metadata['namespace'],
        'default:image': container.get('image'),
        'default:status': status,
        'default:status_message': statusMessage,
        'default:container_id': container_id,
        'default:container_name': container_name
    }

    # rundeck attributes
    data = default_settings
    data['hostname'] = default_settings['default:pod_id']
    data['terminated'] = terminated

    # Add labels as its own map of node attributes.
    if pod_labels is not None:
        for key, value in pod_labels.items():
            data['labels:' + key] = value

    # Initialize custom attributes with ordinal position of this pod within its parent.
    custom_attributes = {'index': index}

    # Custom mapping attributes. Resolved after labels are merged so a mapping can
    # name any node attribute as its source -- default:*, labels:*, hostname.
    if config['mappings']:
        log.debug('Mapping: %s', config['mappings'])

        for mapping in config['mappings']:
            mapping_array = dict(s.split('=', 1) for s in mapping.split())

            for key, value in mapping_array.items():
                if ".selector" in key:
                    attribute = key.replace(".selector", "")
                    custom_attribute = data.get(value)

                    # `is not None` rather than a truth test: a Kubernetes label
                    # may legitimately have an empty value, and dropping the
                    # mapping in that case loses an attribute whose source does
                    # exist. A missing source still resolves to None and is
                    # skipped.
                    if custom_attribute is not None:
                        custom_attributes[attribute] = custom_attribute

        log.debug('Custom Attributes: %s', custom_attributes)

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
            attribute = tag.replace("tag.selector=", "")
            custom_tag = data.get(attribute)

            # A selector naming an attribute this pod does not have -- a label
            # only some pods carry, or an attribute that is legitimately unset,
            # such as default:status_message on a healthy pod -- omits the tag
            # for this node. Indexing instead raised KeyError out of main(), so
            # a single unlabelled pod emptied the entire node source.
            if custom_tag is None:
                log.debug("No value for tag selector %r; tag omitted", attribute)
                continue

            # str() because not every node attribute is a string: terminated is
            # a bool, and joining it raised TypeError.
            final_tags.append(str(custom_tag))
        else:
            final_tags.append(tag)

    data['tags'] = ','.join(final_tags)

    if custom_attributes:
        data = dict(list(data.items()) + list(custom_attributes.items()))

    data.update(config['defaults'])

    # nodename is left to the caller: main() renders it only once the pod is
    # known to be kept and has its final index, so the template can reference
    # ${index}. Any explicit nodename from Custom Mapping or Default attributes
    # is already in data by this point and render_nodename honours it.
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

    one_per_workload = os.environ.get('RD_CONFIG_ONE_PER_WORKLOAD') == 'true'

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
        'tags': [t for t in tags.split(',') if t],
        'mappings': mappingList.split(',') if mappingList else [],
        'defaults': dict(token.split('=') for token in shlex.split(defaults or '')),
        'emoticon': boEmoticon,
        'config_file': os.environ.get('RD_CONFIG_CONFIG_FILE'),
        'nodename_format': os.environ.get('RD_CONFIG_NODENAME_FORMAT'),
    }

    node_set = []

    # Count child pods of a (possibly autoscaling) ReplicaSet or other parent.
    # 'emitted' tracks which workloads have already contributed a node when
    # one_per_workload is enabled.
    parents = {}
    emitted = set()

    try:
        ret = collect_pods_from_api(namespace_filter, label_selector,
                                    field_selector, use_cache=use_cache)
    except ApiException as e:
        log.error("Kubernetes API error (HTTP %s): %s", e.status, e.reason)
        if e.body:
            log.error("Response body: %s", e.body)
        sys.exit(1)

    for i in ret:
        metadata = i['metadata']
        pod_name = metadata['name']
        namespace = metadata['namespace']
        labels = metadata.get('labels') or {}
        workload = workload_name(metadata, labels)
        for container in i['spec']['containers']:
            container_name = container['name']
            log.debug("%s\t%s\t%s\t%s",
                      i['status'].get('podIP'),
                      namespace,
                      pod_name,
                      container_name)

            group = f"{namespace}/{workload}/{container_name}"

            node_data = nodeCollectData(i, container, config)

            if running:
                # default:status, not status: with emoticons enabled, status
                # starts with the emoticon and never equals "running".
                keep = (node_data["default:status"] or "").lower() == "running"
            else:
                keep = node_data["terminated"] is False

            # With one_per_workload, emit only the first kept pod for each workload and
            # container, so the node list shows a single entry per deployment.
            if keep and one_per_workload:
                if group in emitted:
                    keep = False
                else:
                    emitted.add(group)

            if not keep:
                continue

            # Number pods within their workload -- the owning Deployment/StatefulSet/etc.
            # with the pod-template-hash stripped -- keyed per namespace and container so
            # each container name gets its own sequence, and keeping templated node names
            # unique while two ReplicaSets briefly coexist on a rollout.
            #
            # Numbering runs after the filter so a pod that is not emitted does not
            # consume an index. Otherwise a workload whose first pod is Terminated emits
            # nodes numbered 2 and 3, and "index == 1" -- the documented way to target a
            # single replica -- matches nothing.
            parents[group] = parents.get(group, 0) + 1
            node_data['index'] = parents[group]

            # Rendered here rather than in nodeCollectData so the template can reference
            # ${index} after it is final.
            node_data['nodename'] = render_nodename(node_data, config)

            node_set.append(node_data)

    print(json.dumps(node_set, sort_keys=True))


if __name__ == '__main__':
    main()
