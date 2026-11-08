FROM mcr.microsoft.com/dotnet/aspnet:8.0-jammy

ARG DEBIAN_FRONTEND=noninteractive
ARG ONESCRIPT_VERSION=2.2.0
ARG VRUNNER_VERSION=3.0.2
ARG VANESSA_ADD_VERSION=6.8.0

ENV LANG=ru_RU.UTF-8 \
    LANGUAGE=ru_RU:ru \
    LC_ALL=ru_RU.UTF-8 \
    DISPLAY=:99 \
    OSCRIPTBIN=/usr/local/bin \
    PATH=/opt/onescript/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl unzip xz-utils locales \
      xvfb xauth x11-utils \
      libwebkit2gtk-4.0-37 libgtk-3-0 libxtst6 libxrender1 libfontconfig1 \
      libnss3 libasound2 libenchant-2-2 fonts-dejavu-core \
      policykit-1 zenity \
    && locale-gen ru_RU.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

RUN VERSION_PATH="$(printf '%s' "$ONESCRIPT_VERSION" | tr '.' '_')" \
    && curl -fsSL "https://oscript.io/downloads/${VERSION_PATH}/fdd/x64" \
      -o /tmp/onescript.zip \
    && mkdir -p /opt/onescript \
    && unzip -q /tmp/onescript.zip -d /opt/onescript \
    && rm /tmp/onescript.zip \
    && chmod +x /opt/onescript/bin/oscript /opt/onescript/bin/opm \
    && ln -s /opt/onescript/bin/oscript /usr/local/bin/oscript

RUN opm install "vanessa-runner@${VRUNNER_VERSION}" \
    && opm install "add@${VANESSA_ADD_VERSION}" \
    && test -x /usr/local/bin/vrunner \
    && test -f /opt/onescript/lib/add/bddRunner.epf

RUN mkdir -p /opt/1c-packages /workspace/project /workspace/export /reports /opt/formeditor
COPY VBParams.json /opt/formeditor/VBParams.json
COPY entrypoint.sh /usr/local/bin/formeditor-smoke-entrypoint
RUN chmod +x /usr/local/bin/formeditor-smoke-entrypoint

WORKDIR /workspace/project
ENTRYPOINT ["/usr/local/bin/formeditor-smoke-entrypoint"]
