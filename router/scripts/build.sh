#!/usr/bin/env bash
# Build the router image on Databrick (the host that owns Portainer endpoint 3).
# Usage: ./scripts/build.sh
set -euo pipefail

SSH_ALIAS="${SSH_ALIAS:-databricks}"
REMOTE_DIR="/tmp/llm-router-src"
IMAGE_TAG="${IMAGE_TAG:-local/llm-router:1.0.0}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ">> Copying source to ${SSH_ALIAS}:${REMOTE_DIR}"
ssh "${SSH_ALIAS}" "rm -rf ${REMOTE_DIR} && mkdir -p ${REMOTE_DIR}"
scp -r "${REPO_DIR}/." "${SSH_ALIAS}:${REMOTE_DIR}/"

echo ">> Building ${IMAGE_TAG} on ${SSH_ALIAS}"
ssh "${SSH_ALIAS}" "cd ${REMOTE_DIR} && docker build -t ${IMAGE_TAG} ."

echo ">> Image present:"
ssh "${SSH_ALIAS}" "docker images ${IMAGE_TAG}"
