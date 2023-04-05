# Docker rundeck environment

Use this environment to test the plugin
You need a kubernetes environment configured in your host machine (`$HOME/.kube/config`)
That config will be shared with the container

## Copy the plugin 

In the root folder
````
./gradlew build
cp build/libs/kubernetes-X.Y.Z.zip docker-test/rundeck/plugins
````

## Run the environment

```
cd docker-test
docker-compose build
docker-compose up -d
```

## Access the environment

* go to http://localhost:4440/
* you will see a project called `Kubernetes-Demo` with resource model , node executor, and jobs configured

