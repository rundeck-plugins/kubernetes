#!/usr/bin/env python -u
import argparse
import logging
import sys
import os
from kubernetes import client,config
from kubernetes.client import Configuration
from kubernetes.client.apis import core_v1_api
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')

parser = argparse.ArgumentParser(
    description='Execute a command string in the container.')
parser.add_argument('pod', help='Pod')


args = parser.parse_args()

config_file = None

if os.environ.get('RD_CONFIG_DEBUG') == 'true':
    log.setLevel(logging.DEBUG)
    log.debug("Log level configured for DEBUG")


url=None
if os.environ.get('RD_CONFIG_URL'):
    url  = os.environ.get('RD_CONFIG_URL')

verify_ssl=None
if os.environ.get('RD_CONFIG_VERIFY_SSL'):
    verify_ssl  = os.environ.get('RD_CONFIG_VERIFY_SSL')

ssl_ca_cert=None
if os.environ.get('RD_CONFIG_SSL_CA_CERT'):
    ssl_ca_cert  = os.environ.get('RD_CONFIG_SSL_CA_CERT')

token=None
if os.environ.get('RD_CONFIG_TOKEN'):
    field_selector  = os.environ.get('RD_CONFIG_TOKEN')


log.debug("config file")
log.debug(config_file)
log.debug("-------------------")


if config_file: 
	# Configs can be set in Configuration class directly or using helper utility
	log.debug("getting settings from file %s" % args.config_file)

	config.load_kube_config(config_file=args.config_file)
else:

	if url: 
		log.debug("getting settings from pluing configuration")

		configuration = Configuration()
		configuration.host=url
		
		if verify_ssl== 'true':
			configuration.verify_ssl=args.verify_ssl

		if ssl_ca_cert:
			configuration.ssl_ca_cert=args.ssl_ca_cert

		configuration.api_key['authorization'] = token
		configuration.api_key_prefix['authorization'] = 'Bearer'

		client.Configuration.set_default(configuration)
	else:
		log.debug("getting from default config file")
		config.load_kube_config()


api = core_v1_api.CoreV1Api()

name = args.pod
namespace = os.environ.get('RD_NODE_DEFAULT_NAMESPACE')

log.debug( "--------------------------")
log.debug( "Pod Name:  %s" % name)
log.debug( "Namespace: %s " % namespace)
log.debug( "--------------------------")

resp = None
try:
    resp = api.read_namespaced_pod(name=name,
                                   namespace=namespace)
except ApiException as e:
    if e.status != 404:
        print("Unknown error: %s" % e)
        exit(1)

if not resp:
    print("Pod %s does not exits." % name)
    exit(1)

command = os.environ.get('RD_EXEC_COMMAND')
shell = os.environ.get('RD_CONFIG_SHELL')


log.debug( "Command: %s " % command)

# calling exec and wait for response.
exec_command = [
    shell,
    '-c',
    command]

resp = stream(api.connect_get_namespaced_pod_exec, name, namespace,
              command=exec_command,
              stderr=True, stdin=False,
              stdout=True, tty=False)
print(resp)



