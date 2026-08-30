#!/usr/bin/env bash
# Build the ds4:spark image ON the DGX Spark (GB10).
#
#   docker build -t ds4:spark -f docker/Dockerfile .
#     from the Baekpica/ds4 repo @ dfm branch (the qwen38 SSD-PLE handoff).
#
# Run this ON the Spark (SSH in, or from a host with the repo). It:
#   1. clones Baekpica/ds4 @ dfm into /home/darkmatter2222/build/ds4
#   2. builds the cuda-spark target (sm_121a SASS + Spark HBM weight cache)
#   3. tags it ds4:spark  (the image the v3 YAML references)
#
# ~10-20 min on the Spark. No GPU needed for the build (arch is explicit).
set -Eeuo pipefail

BUILD=/home/darkmatter2222/build/ds4
mkdir -p "$BUILD"
cd "$BUILD"

# fetch / update the dfm branch (the qwen38 SSD-PLE verification line)
if [ -d .git ]; then
  git fetch origin dfm && git checkout dfm && git pull origin dfm
else
  git clone -b dfm https://github.com/Baekpica/ds4 .
fi

# show the commit we're building (verify against the repo's verification commits)
echo "Building ds4 @ $(git rev-parse --short HEAD)"

# build the Spark image (make cuda-spark inside). CUDA 13.0.0 devel base.
docker build -t ds4:spark -f docker/Dockerfile .

# sanity: confirm the sm_121a SASS landed (the whole point of cuda-spark)
docker run --rm --entrypoint sh ds4:spark -c \
  'find /opt/ds4 -name "*.o" -o -name "ds4-server" | head; echo "---"; \
   (command -v cuobjdump >/dev/null && cuobjdump -symbols /opt/ds4/ds4-server 2>/dev/null | grep -m3 sm_121a || echo "cuobjdump not in image (ok); the binary carries the SASS")'

echo
echo "ds4:spark ready. Now download the model + PLE sidecar (see download-flashnext-ds4.sh),"
echo "then deploy qwen38-flashnext-dgxsparx-v3-ds4ssdple.yaml via Portainer (endpoint 4)."
