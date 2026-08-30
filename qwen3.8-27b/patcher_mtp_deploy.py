import copy
base = "/usr/local/lib/python3.12/dist-packages/vllm"

# qwen3_5_mtp.py: build the drafter from a DEEP-COPIED (shallow) vllm_config whose
# quant_config is None when running modelopt_fp4 (grafted MTP head is BF16/full-
# width, NOT NVFP4-packed). Qwen3_5DecoderLayer reads vllm_config.quant_config, so
# we null it on a copy rather than a per-module kwarg (which it doesn't accept).
p = base + "/model_executor/models/qwen3_5_mtp.py"
src = open(p).read()
if "drafter_vllm_config" in src:
    print("MTP-drafter patch already applied (idempotent skip)")
else:
    assert "self.quant_config = vllm_config.quant_config" in src
    assert "self.model = Qwen3_5MultiTokenPredictor(\n" in src
    if "import copy" not in src.splitlines()[0]:
        src = "import copy\n" + src
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
    print("MTP-drafter patch applied: drafter built from dequantized vllm_config (modelopt_fp4)")
