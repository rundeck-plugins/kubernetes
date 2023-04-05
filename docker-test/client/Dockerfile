ARG BUILD_DEV_IMAGE
FROM ${BUILD_DEV_IMAGE}

RUN mkdir -p /app/data
COPY projects /app/data/projects/
COPY import.yml /app/data/import.yml
