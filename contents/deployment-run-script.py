#!/usr/bin/env python -u
import logging
import sys
import os
import tempfile
import random
import common


logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='%(levelname)s: %(name)s: %(message)s')
log = logging.getLogger('kubernetes-model-source')

if os.environ.get('RD_JOB_LOGLEVEL') == 'DEBUG':
    log.setLevel(logging.DEBUG)

PY = sys.version_info[0]


def prepare_script(script):
    """
    Simple helper function to reduce lines of code in the huge main loop
    """
    # Python 3 expects bytes string to transfer the data.
    if PY == 3:
        script = script.encode('utf-8')

    invocation = "/bin/bash"
    if 'RD_CONFIG_INVOCATION' in os.environ:
        invocation = os.environ.get('RD_CONFIG_INVOCATION')

    destination_path = "/tmp"

    if 'RD_NODE_FILE_COPY_DESTINATION_DIR' in os.environ:
        destination_path = os.environ.get('RD_NODE_FILE_COPY_DESTINATION_DIR')

    temp = tempfile.NamedTemporaryFile()
    destination_file_name = os.path.basename(temp.name)
    full_path = destination_path + "/" + destination_file_name

    return script, full_path, temp, destination_path, destination_file_name, invocation


def main():
    """
    Runs a script on a randomly selected pod from the deployment. Optionally retries n times until success.
    """

    # start with setting up all paths/variables
    common.connect()
    [deployment_name, namespace, container] = common.get_core_node_parameter_list()
    retries_before_failure = int(os.environ.get('RD_CONFIG_RETRYBEFOREFAILING', 0))
    pods_for_deployment = common.get_active_pods_for_deployment(name=deployment_name, namespace=namespace)
    script = os.environ.get('RD_CONFIG_SCRIPT')
    script, full_path, temp, destination_path, destination_file_name, invocation = prepare_script(script)
    temp.write(script)
    temp.seek(0)
    if not container:
        container = common.resolve_container_for_pod(pods_for_deployment[0], namespace)

    # loop until we've reached the max number of retries (default none)
    for i in range(retries_before_failure + 1):
        # randomly select one of the pods
        pod_name = random.choice(pods_for_deployment)
        log.debug("iteration %d", i)
        common.log_pod_parameters(log, {'name': pod_name, 'namespace': namespace, 'container_name': container})

        try:
            log.debug("coping script from %s to %s", temp.name, full_path)

            common.copy_file(name=pod_name,
                             namespace=namespace,
                             container=container,
                             source_file=temp.name,
                             destination_path=destination_path,
                             destination_file_name=destination_file_name
                             )

            permissions_command = ["chmod", "+x", full_path]
            log.debug("setting permissions %s", permissions_command)
            resp = common.run_command(name=pod_name,
                                      namespace=namespace,
                                      container=container,
                                      command=permissions_command
                                      )

            if resp.peek_stdout():
                print(resp.read_stdout())

            if resp.peek_stderr():
                print(resp.read_stderr())
                continue


            # calling exec and wait for response.
            exec_command = invocation.split(" ")
            exec_command.append(full_path)

            if 'RD_CONFIG_ARGUMENTS' in os.environ:
                arguments = os.environ.get('RD_CONFIG_ARGUMENTS')
                exec_command.append(arguments)

            log.debug("running script %s", exec_command)

            resp, error = common.run_interactive_command(name=pod_name,
                                                         namespace=namespace,
                                                         container=container,
                                                         command=exec_command
                                                         )
            if error:
                log.error("error running script on iteration %d", i)
                continue

            rm_command = ["rm", full_path]
            log.debug("removing file %s", rm_command)
            resp = common.run_command(name=pod_name,
                                      namespace=namespace,
                                      container=container,
                                      command=rm_command
                                      )
            if resp.peek_stdout():
                log.debug(resp.read_stdout())

            if resp.peek_stderr():
                log.debug(resp.read_stderr())
                continue
        except Exception as e:
            log.error(e)
            continue
        temp.close()
        log.info("Job successful on iteration %d", i)
        sys.exit(0)
    # if we have not reached exit 0 (at the end of the loop iteration), it means no single execution succeeded
    log.error("unable to run script on any of the nodes")
    temp.close()
    sys.exit(1)


if __name__ == '__main__':
    main()
