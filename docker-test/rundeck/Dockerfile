ARG RUNDECK_IMAGE
FROM ${RUNDECK_IMAGE}

USER root
RUN sudo apt-get update
RUN sudo apt-get install -y -qq --no-install-recommends wget git curl jq iputils-ping sysstat

RUN apt-get -y install python3-pip && \
    pip3 install --upgrade pip

RUN ln -s /usr/bin/python3 /usr/bin/python

RUN pip3 install kubernetes

USER rundeck

COPY plugins/. /home/rundeck/libext
