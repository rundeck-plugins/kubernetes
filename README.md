# Rundeck Kubernetes Plugin

This project provides integration between Rundeck and Kubernetes. This project contains a number of providers allowing job writers to use steps to call various API actions in Kubernetes.

Use cases:

* Create Kubernetes Deployments, Services and Jobs
* Run ad hoc command executions inside Kubernetes containers.


## Requirements

### Python Version

This plugin requires **Python 3.10 or newer**. The plugin is tested on Python 3.10, 3.11, 3.12, 3.13, and 3.14.

**Note:** Python 3.9 reached end-of-life in October 2025 and is no longer supported.

### Python Dependencies

This plugin requires the following Python packages to be installed **on the server where Rundeck executes** (either your Rundeck server or your Runner nodes if using remote execution):

- **kubernetes** >= 35.0.0 - The official Kubernetes Python client
- **urllib3** >= 2.6.3 - HTTP client library
- **pyyaml** - YAML parser and emitter
- **packaging** >= 20.0 - Version comparison utilities

**Installation location:**
- **Rundeck server**: If running jobs locally on the Rundeck server
- **Runner nodes**: If using Rundeck Enterprise with remote execution
- **Both**: If you have a mixed environment

You can install all dependencies using:

```bash
pip install .
```

Or install individual packages directly:

```bash
pip install 'kubernetes>=35.0.0'
```

**Version 35.0.0+ is required** to address security vulnerabilities in transitive dependencies. This version removes the dependency on `google-auth`, which had a vulnerable `pyasn1` dependency (CVE-2026-23490).

You can verify your installation with:

```bash
python -m pip list | grep kubernetes
```

Further information: [https://github.com/kubernetes-client/python](https://github.com/kubernetes-client/python)

### Kubernetes Cluster Compatibility

This plugin requires the Kubernetes Python client library version **35.0.0 or newer**.

The Kubernetes Python client is generally **backwards compatible** with older Kubernetes clusters. For the most accurate and up-to-date information about which Kubernetes API/server versions are supported by a given client version, refer to the upstream compatibility documentation:

- [Kubernetes Python Client Compatibility](https://github.com/kubernetes-client/python#compatibility)

In practice, upgrading the client library typically does not require upgrading your Kubernetes cluster, but you should verify compatibility against the upstream documentation and test in a non-production environment before making changes.

### Upgrading from Previous Plugin Versions

If you're upgrading from a previous version of this plugin (v2.0.16 or earlier), you **must** upgrade your Python dependencies to avoid security vulnerabilities.

**Run this command on each server where Rundeck executes jobs:**

```bash
pip install --upgrade 'kubernetes>=35.0.0'
# or if pip3 is your command:
pip3 install --upgrade 'kubernetes>=35.0.0'
```

**Where to run this command:**
- **Rundeck server**: If jobs run locally on your Rundeck server
- **Each Runner node**: If using Rundeck Enterprise with remote execution
- **Both**: If you have a mixed environment

**Why the upgrade is required:**
- Previous versions allowed any kubernetes client version, including older versions with security vulnerabilities
- Version 35.0.0+ eliminates CVE-2026-23490 (High severity DoS vulnerability) by removing the vulnerable dependency chain
- The upgrade is backwards compatible with your existing Kubernetes clusters

**What won't break:**
- Your existing Kubernetes cluster version (no cluster upgrade required)
- Your existing plugin configurations
- Your existing Rundeck jobs and workflows
- Communication with older Kubernetes API versions (v1.25, v1.28, v1.30, etc.)

**What happens if you don't upgrade:**
- Jobs will continue to work (no immediate breakage)
- A security warning will appear in job logs on every execution
- Your installation remains vulnerable to CVE-2026-23490

**What changes:**
- The Python kubernetes client library must be upgraded on all execution nodes
- Any custom scripts or automation that install dependencies will need to use the new version

## Build and Install

Run `gradle build` to build the zip file. Then, copy the zip file to the `$RDECK_BASE\libext` folder.

## Development Setup

Install the project with development dependencies:

```sh
pip install -e '.[dev]'
```

This installs the project in editable mode along with testing tools (pytest).

## Testing

You can run tests directly with pytest:

```sh
pytest
```

Or use Tox, which manages its own virtual environment:

```sh
pip install tox
tox
```

## Authentication

By default, and if any authentication parameters are not set, the plugin will check the `~/.kube/config` file to get the authentication parameters.

Otherwise, you can set the following parameters:

* **Kubernetes Config File Path**: a custom path for the kubernetes config file
* **Cluster URL**: Kubernetes Cluster URL
* **Kubernetes API Token**:  Token to connect to the kubernetes API
* **Verify SSL**: Enable/Disable the SSL verification
* **SSL Certificate Path**: SSL Certificate Path for SSL connections

## Resource Model

This plugin allows getting the container pods from kubernetes as rundeck nodes.

* **Default attributes**: List of key=value pairs, example: username=root
* **Custom Mapping**: Custom mapping adding on the rundeck nodes, for example: ```nodename.selector=default:name,hostname.selector=default:pod_id```

* **Tags**: List of tags. You can add static and custom tags, for example:
```tag.selector=default:image, tag.selector=default:status, kubernetes```

* **Namespace** Retrieve only pods from a desired namespace. (An empty value results in listing pods from all namespaces)
For example: `default` will result on listing the pods on "default" namespace.
* **Field Selector**: Filter the list of pods using a response's API fields. For further information check SDK docs [here](https://github.com/kubernetes-client/python/blob/fd5a0c49259e83d928535dd66ab083ddb92ccecf/kubernetes/docs/CoreV1Api.md#return-type-116).
For example: ```metadata.uid=123``` will show the pod with uid 123.
* **Just Running Pods?**: Filter by running pods

This plugin generates a list of `default` pod's attributes in order to reference them on the custom config parameters of the plugin (eg: default:status, default:image). The following list are the default available attributes:

```
default:pod_id: Pod ID,
default:host_id: Host ID,
default:started_at: started At,
default:name: Pod Name,
default:namespace: Pod namespace,
default:labels: Deployments labels,
default:image: Image,
default:status: Pod Status,
default:status_message: Pod Status message,
default:container_id: Container ID,
default:container_name: Container Name
```

For example, if you want to add a custom tag for the container's image name, use `tag.selector=default:image` on the `Tags` config attribute. Or if you want to define the hostname node attribute using the POD ID, use `hostname.selector=default:pod_id` on the `Custom Mapping` config attribute.


## Node Executor
This plugin allows run commands/scripts to a container pod from rundeck.

**Configurations:**

* **Shell**: Shell used on the POD to run the command. Default value: /bin/bash
* **Debug?**: Write debug messages to stderr


## File Copier
This plugin allows copying files from Rundeck to a pod, including script, text, and binary files.

**Configurations:**

* **Shell**: Shell used on the POD to run the command. Default value: /bin/bash
* **Debug?**: Write debug messages to stderr


## Workflow Steps

The following steps plugins allow you to deploy/un-deploy applications and run/re-run jobs on kubernetes. For example, you can create deployment, services, ingress, etc and update or delete those kubernetes resources.

### Create / Update / Delete / Check / Wait a Deployment
These steps manage deployment resources, you can create, update or delete a deployment and check its status.

Also, you have a step to wait for a deployment to be ready when the deployment is created. These require that the deployment define a `Readiness Probe` (further information [here](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-probes/#define-readiness-probes))

### Create / Update / Delete Services

These steps manage services resources, you can create, update or delete a service.


### Create / Delete / Re-run Jobs

These steps manage services resources, you can create or delete a Job.

Also, you can re-run jobs that are already created. Kubernetes doesn't allow re-run jobs, so what this step does is get the job definition, delete it, and creating it again.

### Generic Steps

These steps provide a generic way to create/delete resources on kubernetes using a yaml script. The resources that this plugin allows creating are:

* Deployment
* Service
* Ingress
* Job
* StorageClass
* PersistentVolume
* PersistentVolumeClaim
* Secret
