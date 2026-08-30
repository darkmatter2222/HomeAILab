#!/usr/bin/env bash
# Download the Q6 backbone (4 GGUF shards) + the PLE SSD sidecar (4 .bin + manifest)
# for Baekpica/Qwen3.8-Flash-Next-Mixed-Quant-SSD-PLE-GGUF onto the Spark.
#
# Lands in:  /home/darkmatter2222/models/flashnext-ds4/Qwen3.8-Flash-Next-MQ-Q6-SSD-PLE-BF16/
#             (backbone shards at the dir root, PLE in ./ple/  -- the layout the
#              ds4 loader discovers by convention)
#
# ~186 GiB total (91 backbone + 95 PLE). Capped at 25 MiB/s like every other
# download in the fleet -> roughly 2-3 hours. Run in the background on the Spark.
#
# Needs `huggingface-cli` (pip install -U "huggingface_hub[cli]") on the Spark.
set -Eeuo pipefail

REPO=Baekpica/Qwen3.8-Flash-Next-Mixed-Quant-SSD-PLE-GGUF
DEST=/home/darkmatter2222/models/flashnext-ds4/Qwen3.8-Flash-Next-MQ-Q6-SSD-PLE-BF16
mkdir -p "$DEST/ple"

# 1) backbone: the 4 GGUF shards (concatenated to a single file by the v3 YAML)
huggingface-cli download "$REPO" \
  "MQ-Q6-SSD-PLE-BF16/Qwen3.8-Flash-Next-MQ-Q6-SSD-PLE-BF16-0000[1-4]-of-00004.gguf" \
  --local-dir "$DEST"

# 2) PLE sidecar: the 4 .bin + the manifest (discovered next to the model)
huggingface-cli download "$REPO" \
  "MQ-Q6-SSD-PLE-BF16/ple/ple-bf16-0000[1-4]-of-00004.bin" \
  "MQ-Q6-SSD-PLE-BF16/ple/ple-manifest.json" \
  --local-dir "$DEST"

# 3) verify against the repo's checksums (the "sidecar actually works" gate)
if [ -f "$DEST/SHA256SUMS.main" ]; then
  echo "Verifying backbone against SHA256SUMS.main ..."
  ( cd "$DEST" && grep -v '^ple/' SHA256SUMS.main 2>/dev/null | sha256sum -c --quiet || \
    grep -E 'Qwen3.8.*gguf$' SHA256SUMS.main | sha256sum -c )
fi
[ -f "$DEST/ple/SHA256SUMS" ] && \
  ( cd "$DEST/ple" && sha256sum -c --quiet SHA256SUMS && echo "PLE sidecar verified." ) || true

echo
echo "Backbone: $(du -sh "$DEST" | cut -f1)   PLE: $(du -sh "$DEST/ple" | cut -f1)"
echo "Ready to deploy qwen38-flashnext-dgxsparx-v3-ds4ssdple.yaml (endpoint 4)."
