#!/usr/bin/env python -u
import argparse
import logging
import sys
import os
from kubernetes import client,config
from kubernetes.client import Configuration
import json
import shlex



logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')


class JsonQuery(dict):
    def get(self, path, default = None):
        keys = path.split(".")
        val = None

        for key in keys:
            if val:
                if isinstance(val, list):
                    val = [ v.get(key, default) if v else None for v in val]
                else:
                    val = val.get(key, default)
            else:
                val = dict.get(self, key, default)

            if not val:
                break;

        return val


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
        field_selector = os.environ.get('RD_CONFIG_TOKEN')

    log.debug("config file")
    log.debug(config_file)
    log.debug("-------------------")

    if config_file:
        # Configs can be set in Configuration class directly or using helper utility
        log.debug("getting settings from file %s" % config_file)

        config.load_kube_config(config_file=config_file)
    else:

        if url:
            log.debug("getting settings from pluing configuration")

            configuration = Configuration()
            configuration.host = url

            if verify_ssl == 'true':
                configuration.verify_ssl = args.verify_ssl

            if ssl_ca_cert:
                configuration.ssl_ca_cert = args.ssl_ca_cert

            configuration.api_key['authorization'] = token
            configuration.api_key_prefix['authorization'] = 'Bearer'

            client.Configuration.set_default(configuration)
        else:
            log.debug("getting from default config file")
            config.load_kube_config()

def nodeCollectData(pod, defaults, taglist, mappingList):
    tags = []
    tags.extend(taglist.split(','))

    status = pod.status.phase
    statusMessage = None
    startedAt = None

    terminated=False
    for statuses in pod.status.container_statuses:
        if statuses.state.running is not None:
            status="running"
            if statuses.state.running.started_at:
                startedAt=statuses.state.running.started_at.strftime("%Y-%m-%d %H:%M:%S")

        if statuses.state.waiting is not None:
            status = "waiting"

        if statuses.state.terminated is not None:
            terminated=True
            status = "terminated"

    if terminated==False:
        for info in pod.status.conditions:
            if (info.status == 'False'):
                status= info.reason
                statusMessage = info.message

    labels = []
    for keys, values in pod.metadata.labels.items():
        labels.append(keys + ":" + values)

    default_settings = {
        'default:pod_id': pod.status.pod_ip,
        'default:host_id': pod.status.host_ip,
        'default:started_at': startedAt,
        'default:name': pod.metadata.name,
        'default:labels': ','.join(labels),
        'default:namespace': pod.metadata.namespace,
        'default:image': pod.status.container_statuses[0].image,
        'default:status': status,
        'default:status_message': statusMessage,
        'default:container_id': pod.status.container_statuses[0].container_id,
        'default:container_name': pod.status.container_statuses[0].name
    }

    mappings = []
    custom_attributes={}

    #custom mapping attributes
    if mappingList:
        log.debug('Mapping: %s' % mappingList)
        mappings.extend(mappingList.split(','))

        for mapping in mappings:
            mapping_array = dict(s.split('=', 1) for s in mapping.split())

            for key, value in mapping_array.items():
                if key.find(".selector"):

                    attribute= key.replace(".selector" ,"")
                    custom_attribute=None
                    
                    #take the values from default
                    if "default:" in value:
                        custom_attribute=default_settings[value]
                    else:
                    #taking the values from docker inspect
                        for item in json:
                            custom_attribute=JsonQuery(item).get(value)

                    if custom_attribute:
                        custom_attributes[attribute] = custom_attribute

        log.debug('Custom Attributes: %s' % custom_attributes)




    # rundeck attributes
    data = default_settings
    data['nodename']=default_settings['default:name']
    data['hostname']=default_settings['default:pod_id']
    data['terminated'] = terminated

    emoticon=""
    if default_settings['default:status']=="running":
        emoticon = u'\U0001f44d'
    if default_settings['default:status']=="terminated":
        emoticon = u'\U00002705'
    if default_settings['default:status']=="ContainersNotReady":
        emoticon = u'\U0000274c'
    if default_settings['default:status']=="waiting":
        emoticon = u'\U0000274c'

    data['status'] = emoticon + " " + default_settings['default:status']

    description=emoticon  + " " + default_settings['default:status']
    if default_settings['default:status_message'] :
        description = description + "(" + default_settings['default:status_message'] + ")"

    data['description'] = description

    final_tags = ["pods"]
    for tag in tags:        
        if "tag.selector=" in tag:
            custom_tag=data[tag.replace("tag.selector=" ,"")]
            final_tags.append(custom_tag)
        else:
            final_tags.append(tag)

    data['tags'] = ','.join(final_tags)

    if custom_attributes:
        data = dict(data.items() + custom_attributes.items())

    data.update(dict(token.split('=') for token in shlex.split(defaults)))

    return data


parser = argparse.ArgumentParser(
    description='Execute a command string in the container.')

args = parser.parse_args()

config_file = None

if os.environ.get('RD_CONFIG_DEBUG') == 'true':
    log.setLevel(logging.DEBUG)
    log.debug("Log level configured for DEBUG")



connect()

tags=os.environ.get('RD_CONFIG_TAGS')
mappingList=os.environ.get('RD_CONFIG_MAPPING')
defaults=os.environ.get('RD_CONFIG_ATTRIBUTES')

running = False
if os.environ.get('RD_CONFIG_RUNNING') == 'true':
    running = True


field_selector=None
if os.environ.get('RD_CONFIG_FIELD_SELECTOR'):
    field_selector  = os.environ.get('RD_CONFIG_FIELD_SELECTOR')


node_set = []
mappingList=None
defaults=None

v1=client.CoreV1Api()
ret = v1.list_pod_for_all_namespaces(watch=False,field_selector=field_selector)
for i in ret.items:
    log.debug("%s\t%s\t%s" % (i.status.pod_ip, i.metadata.namespace, i.metadata.name))

    node_data = nodeCollectData(i,
                                defaults,
                                tags,
                                mappingList)


    if running == False:
        if(node_data["terminated"]==False):
            node_set.append(node_data)

    if running == True:
        if node_data["status"]=="Running":
            node_set.append(node_data)


print json.dumps(node_set, indent=4, sort_keys=True)

