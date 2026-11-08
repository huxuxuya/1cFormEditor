FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive LANG=ru_RU.UTF-8 LC_ALL=ru_RU.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip python3 openjdk-17-jre-headless locales \
    xvfb xauth x11-utils fonts-dejavu-core libgtk-3-0 libwebkit2gtk-4.0-37 \
    libxtst6 libxrender1 libfontconfig1 libnss3 libasound2 libenchant-2-2 \
    libsm6 libice6 libgsf-1-114 libgssapi-krb5-2 \
    && locale-gen ru_RU.UTF-8 \
    && printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && chmod +x /usr/sbin/policy-rc.d \
    && rm -rf /var/lib/apt/lists/*

# Supply the licensed platform's common, server and full client .deb packages
# for one release and architecture in the build context's platform/ directory.
RUN --mount=type=bind,source=platform,target=/tmp/platform,readonly \
    apt-get update && apt-get install -y /tmp/platform/*.deb \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /project
ENTRYPOINT ["/bin/bash", "/project/docker/1c-release/entrypoint.sh"]
