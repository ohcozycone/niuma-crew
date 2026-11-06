# Supply a verified digest, for example python:3.12-slim-bookworm@sha256:...
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends procps git nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 worker && useradd --uid 1000 --gid 1000 --create-home worker \
    && install -d -o 1000 -g 1000 -m 700 /workspace /outputs \
    && install -d -o 0 -g 0 -m 755 /inputs
WORKDIR /workspace
CMD ["sleep", "infinity"]
