import copy
base = "/usr/local/lib/python3.12/dist-packages/vllm"

# ---- qwen3_5_mtp.py: build the drafter (Qwen3_5MultiTokenPredictor ->
#      Qwen3_5DecoderLayer) with a DEEP-COPIED vllm_config whose quant_config
#      is None when running modelopt_fp4 (grafted MTP head is BF16/full-width,
#      NOT NVFP4-packed). Qwen3_5DecoderLayer reads vllm_config.quant_config, so
#      we can't pass a per-module kwarg; mutate a copy instead.
p = base + "/model_executor/models/qwen3_5_mtp.py"
src = open(p).read()
assert "self.quant_config = vllm_config.quant_config" in src
assert "self.model = Qwen3_5MultiTokenPredictor(\n" in src
assert "vllm_config=vllm_config, prefix=maybe_prefix(prefix, \"mtp\")" in src
# add `import copy` (idempotent)
if "import copy" not in src.splitlines()[0]:
    src = "import copy\n" + src
# deep-copy the vllm_config and null its quant_config for modelopt_fp4
src = src.replace(
    "self.quant_config = vllm_config.quant_config",
    "self.quant_config = vllm_config.quant_config\n"
    "        # The grafted MTP head (layers.0 + lm_head) ships BF16/full-width, NOT\n"
    "        # NVFP4-packed. Qwen3_5DecoderLayer reads vllm_config.quant_config,\n"
    "        # so build the drafter with a copy whose quant_config is None.\n"
    "        _drafter_vllm_config = vllm_config\n"
    "        if (self.quant_config and self.quant_config.get_name() == 'modelopt_fp4'):\n"
    "            _drafter_vllm_config = copy.copy(vllm_config)\n"
    "            _drafter_vllm_config.quant_config = None",
    1,
)
src = src.replace(
    "self.model = Qwen3_5MultiTokenPredictor(\n"
    "            vllm_config=vllm_config, prefix=maybe_prefix(prefix, \"mtp\")\n"
    "        )",
    "self.model = Qwen3_5MultiTokenPredictor(\n"
    "            vllm_config=_drafter_vllm_config, prefix=maybe_prefix(prefix, \"mtp\")\n"
    "        )",
    1,
)
open(p, "w").write(src)
print("qwen3_5_mtp.py patched: drafter built from dequantized vllm_config (modelopt_fp4)")

# ---- parameter.py: PRINTR probe (no skip) on the 2 fused load asserts, so any
#      remaining shape mismatch is captured.
p2 = base + "/model_executor/parameter.py"
src2 = open(p2).read()
anchor = "        assert param_data.shape == loaded_weight.shape"
n = src2.count(anchor)
probe = (
    anchor
    + "\n        if param_data.shape != loaded_weight.shape:\n"
    "            import sys as _s\n"
    "            _m=\"PROBE-MISMATCH name=%s outdim=%s slice=%s loaded=%s packed=%s type=%s\" % (getattr(self,'original_attribute_name','?'), getattr(self,'output_dim','?'), tuple(param_data.shape), tuple(loaded_weight.shape), getattr(self,'packed_dim','?'), type(self).__name__)\n"
    "            _s.stderr.write(_m); _s.stderr.flush()\n"
    "            try:\n                open('/probe_out.txt','a').write(_m+chr(10))\n            except Exception: pass\n"
)
out = []
count = 0
for line in src2.splitlines(keepends=True):
    if count < 2 and line == anchor + "\n":
        out.append(line)
        for pl in probe.splitlines(keepends=True)[1:]:
            out.append(pl)
        count += 1
    else:
        out.append(line)
open(p2, "w").write("".join(out))
print("parameter.py probe inserted in", count, "of", n, "assert sites")
