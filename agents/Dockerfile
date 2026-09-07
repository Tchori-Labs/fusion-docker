# Agent toolchain layer on top of the clean fusion image, for deployments
# whose coding agents run INSIDE the container. Root only for installs.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root
# Playwright 1.61.1 / Chromium revision 1228, Debian 12 runtime union.
# Keep this explicit: the agents image must not download a project browser.
ARG PLAYWRIGHT_VERSION=1.61.1
ARG PLAYWRIGHT_CHROMIUM_REVISION=1228
ARG PLAYWRIGHT_CHROMIUM_DEPS="\
  libglib2.0-0 \
  libnss3 \
  libnspr4 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libatspi2.0-0 \
  libcups2 \
  libdbus-1-3 \
  libx11-6 \
  libxcomposite1 \
  libxdamage1 \
  libxext6 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libxcb1 \
  libxkbcommon0 \
  libpango-1.0-0 \
  libcairo2 \
  libasound2"
LABEL org.opencontainers.image.playwright-version="${PLAYWRIGHT_VERSION}" \
      org.opencontainers.image.playwright-chromium-revision="${PLAYWRIGHT_CHROMIUM_REVISION}"

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
  && install -m 0755 -d /etc/apt/keyrings \
  && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
  && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
  && apt-get update && apt-get install -y --no-install-recommends gh bubblewrap ${PLAYWRIGHT_CHROMIUM_DEPS} \
  && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code@2.1.208 @openai/codex@0.144.3
USER node
