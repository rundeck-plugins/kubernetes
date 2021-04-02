#!/usr/bin/env python -u
import logging
import sys
import os
import common
from kubernetes import client
from kubernetes.client.rest import ApiException


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-service-delete')


def main():

    if os.environ.get('RD_CONFIG_DEBUG') == 'true':
        log.setLevel(logging.DEBUG)
        log.debug("Log level configured for DEBUG")

    data = {}

    data["name"] = os.environ.get('RD_CONFIG_NAME')
    data["namespace"] = os.environ.get('RD_CONFIG_NAMESPACE')

    common.connect()

    k8s_client = client.BatchV1Api()

    try:

        ## get pods from job
        label_selector = "job-name="+data["name"]
        pretty = 'true'

        v1 = client.CoreV1Api()
        ret = v1.list_pod_for_all_namespaces(
            watch=False,
            label_selector=label_selector
        )

        print("pods found: %s" % len(ret.items))

        for i in ret.items:
            print("Removing pod %s" % (i.metadata.name))

        watch = True

        try:
            api_response = v1.delete_collection_namespaced_pod(data["namespace"],
                                                               pretty=pretty,
                                                               label_selector=label_selector,
                                                               watch=watch)

            print(common.parseJson(api_response))
        except ApiException as e:
            print("Exception when calling CoreV1Api->delete_collection_namespaced_pod: %s\n" % e)


        body = client.V1DeleteOptions(api_version='v1', kind="DeleteOptions", propagation_policy="Background")

        api_response = k8s_client.delete_namespaced_job(
            name=data["name"],
            namespace=data["namespace"],
            body=body,
            pretty=pretty
        )

        print(common.parseJson(api_response.status))

    except ApiException:
        log.exception("Exception when calling delete_namespaced_job:")
        sys.exit(1)


if __name__ == '__main__':
    main()
