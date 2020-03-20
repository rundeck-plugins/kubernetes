# Rundeck Kubernetes Plugin

This project provides integration between Rundeck and Kubernetes. This project contains a number of providers allowing job writers to use steps to call various API actions in Kubernetes.

Use cases:

* Create Kubernetes Deployments, Services and Jobs
* Run ad hoc command executions inside Kubernetes containers.


## Requirements

These plugins require the python kubernetes SDK to be installed on the rundeck server.
For example, you can install it using `pip install kubernetes`.

The Python Kubernetes API client requires version 11 of the library. You can confirm it with `python -m pip list | grep kubernetes`.

Further information here: [https://github.com/kubernetes-client/python](https://github.com/kubernetes-client/python).

### Authentication for Tectonic Environments.
There is a pull request [work](https://github.com/kubernetes-client/python-base/pull/48) for the kubernetes python SDK to support authenticating with the kubernetes API using OIDC (which is used by tectonic).

For now, you can install the kubernetes python SDK from this repo to have the OIDC support:

```
git clone --recursive https://github.com/ltamaster/python
cd python
python setup.py install

```

## Build and Install

Run `gradle build` to build the zip file. Then, copy the zip file to the `$RDECK_BASE\libext` folder.


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
* **Custom Mapping**: Custom mapping adding on the rundeck nodes, for example: ```nodename.selector=default:Name,hostname.selector=default:pod_id```

* **Tags**: List of tags. You can add static and custom tags, for example:
```tag.selector=default:image, tag.selector=default:status, kubernetes```

* **Field Selector**: Filter the list of pods using a response's API fields. For further information check SDK docs [here](https://github.com/kubernetes-client/python/blob/fd5a0c49259e83d928535dd66ab083ddb92ccecf/kubernetes/docs/CoreV1Api.md#return-type-116).
For example: ```metadata.namespace=default``` will show the pods of the default namespace.
* **Just Running Pods?**: Filter by running pods

This plugin generate a list of `default` pod's attributes in order to reference them on the custom config parameters of the plugin (eg: default:status, default:image). The following list are the default available attributes:

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
This plugin allows copy files from rundeck to a pod.
For now just script and text files can be copied to a remote pod.

**Configurations:**

* **Shell**: Shell used on the POD to run the command. Default value: /bin/bash
* **Debug?**: Write debug messages to stderr


## Workflow Steps

The following steps plugins allow you to deploy/un-deploy applications and run/re-run jobs on kubernetes. For example, you can create deployment, services, ingress, etc and update or delete those kubernetes resources.

### Create / Update / Delete / Check / Wait a Deployment
Theses steps manage deployment resources, you can create, update or delete a deployment and check its status.

Also, you have a step to wait for a deployment to be ready when the deployment is created. These require that the deployment define a `Readiness Probe` (further information [here](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-probes/#define-readiness-probes))

### Create / Update / Delete Services

Theses steps manage services resources, you can create, update or delete a service.


### Create / Delete / Re-run Jobs

Theses steps manage services resources, you can create or delete a Job.

Also, you can re-run jobs that are already created. Kubernetes doesn't allow re-run jobs, so what this step does is get the job definition, delete it, and creating it again.

### Generic Steps

These steps provide a generic way to create/delete resources on kubernetes using a yaml script. The resources that this plugin allows to create are:

* Deployment
* Service
* Ingress
* Job
* StorageClass
* PersistentVolume
* PersistentVolumeClaim
* Secret
