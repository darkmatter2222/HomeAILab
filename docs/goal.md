# Build a Production-Grade Single-GPU LLM Performance Benchmarking Platform

You are building a complete, production-quality benchmarking platform for **LLM inference performance on a single NVIDIA GPU**.

This is not a proof of concept, notebook, one-off benchmark script, or toy dashboard.

Build the working repository, CLI, benchmark engine, telemetry collectors, adapters, artifact system, report generator, static HTML site, tests, documentation, and schemas.

Do not stop after producing an architecture proposal. Implement it.

---

# 1. Primary Objective

Build a benchmark runner that measures an **already-running LLM deployment** through an OpenAI-compatible API.

Example:

```bash
llmbench run \
  --target http://192.168.1.50:8000/v1 \
  --mode light
```

The benchmark runner is a **child component**.

It MUST NOT:

* deploy a model
* restart a model
* change inference-engine flags
* change quantization
* change context size
* change GPU clocks
* change GPU power limits
* modify the inference server
* reconfigure the deployment
* perform model tuning itself

A separate parent/orchestration program will eventually perform deployment grid searches by changing configurations and then invoking this benchmark runner once for each configuration.

This benchmark runner's responsibility is:

> Given one running model, on one GPU, with one fixed deployment configuration, comprehensively characterize its inference performance and permanently record the result.

The resulting repository will eventually become a public historical catalog of every model/configuration I benchmark.

---

# 2. Research Before Implementation

Before coding the benchmark methodology, perform fresh web research.

Prefer authoritative and current sources.

At minimum research the latest documentation and methodology from:

* NVIDIA AIPerf
* NVIDIA GenAI-Perf history and migration to AIPerf
* NVIDIA DCGM
* NVML
* vLLM production metrics
* llama.cpp / llama-server metrics
* llama.cpp benchmarking methodology
* SGLang metrics
* TensorRT-LLM metrics
* Hugging Face TGI metrics
* MLPerf Inference methodology where applicable
* OpenAI-compatible streaming API behavior
* current best practices for measuring generative AI serving performance

Record important sources in:

```text
docs/benchmark-methodology-sources.md
```

Include source URL, retrieval date, relevant metrics/methodology, and how it influenced this implementation.

Do not blindly copy one benchmarking product.

Use current industry benchmark terminology and formulas wherever possible.

---

# 3. Important Current Benchmarking Direction

Treat NVIDIA AIPerf as an important reference implementation and, where useful, an optional benchmark backend.

However:

**Do not make this project dependent on AIPerf.**

Implement a native OpenAI-compatible streaming benchmark engine that can independently calculate the core measurements.

If AIPerf is installed or enabled, optionally run it as a secondary/reference measurement source and archive its artifacts.

The canonical benchmark repository and canonical metric schema must belong to this project.

The system should be capable of comparing:

1. client-observed metrics
2. inference-server metrics
3. NVIDIA GPU telemetry
4. optional AIPerf metrics

Disagreements should be surfaced, not silently hidden.

Never trust one gauge simply because the engine exposes it.

---

# 4. Scope

This project measures **performance only**.

Do NOT implement:

* HumanEval
* SWE-bench
* reasoning benchmarks
* coding correctness
* MMLU
* math accuracy
* model intelligence
* answer quality
* hallucination testing

Quality evaluation belongs to another system.

This platform answers:

> How well does this exact model deployment perform on this exact GPU using this exact inference configuration?

---

# 5. Initial Engines

Architect engine support through adapters.

Initially provide first-class adapters for:

* vLLM
* llama.cpp / llama-server

Design the adapter interface so these can be added without redesigning the project:

* SGLang
* TensorRT-LLM
* TGI
* Triton
* NVIDIA Dynamo
* arbitrary OpenAI-compatible server

The user may explicitly specify an engine:

```bash
--engine vllm
--engine llamacpp
```

but default behavior should be:

```bash
--engine auto
```

Attempt engine detection using endpoint metadata, metrics, process inspection, container inspection, version endpoints, etc.

The engine detected must become part of the benchmark manifest and all report filtering.

---

# 6. Single GPU Only

This project is explicitly optimized for:

**one deployed model using one GPU.**

Do not design a complicated multi-node or distributed benchmark architecture.

Do not attempt to support:

* tensor parallel multi-GPU deployments
* pipeline parallel deployments
* clusters
* distributed workers
* load-balanced endpoint fleets

If more than one active GPU is discovered for the target deployment, warn clearly that the run is outside the supported benchmark model.

Keep the architecture simple.

---

# 7. Dynamic Target

The target must always be dynamic.

Example:

```bash
llmbench run \
  --target http://hostname:8000/v1 \
  --mode light
```

Support:

```text
/v1/chat/completions
/v1/completions
```

Prefer streaming requests for token-level timing.

Useful CLI options should include approximately:

```bash
llmbench run \
  --target http://host:8000/v1 \
  --model auto \
  --engine auto \
  --mode light \
  --budget 2h \
  --output-root ./benchmarks \
  --ssh-host auto \
  --tokenizer auto \
  --resume
```

Also support things such as:

```text
--target
--model
--engine
--mode
--budget
--output-root
--ssh-host
--ssh-user
--tokenizer
--api-key-env
--metrics-url
--prometheus-url
--max-concurrency
--max-context
--power-cost-per-kwh
--resume
--run-label
--configuration-label
--public
--seed
--verbose
```

Use existing SSH configuration and credentials whenever possible.

Never persist credentials into benchmark artifacts.

---

# 8. Host Introspection

The benchmark machine has credentials allowing it to inspect the GPU host.

Use safe, read-only host inspection.

Support local execution as well as remote inspection over SSH.

Determine as much as possible automatically.

Collect:

## Operating system

* hostname internally, but redact publicly
* OS/distribution
* kernel
* architecture
* uptime where useful
* CPU model
* physical/logical CPU count
* RAM
* swap
* relevant NUMA information
* PCIe topology where available

## NVIDIA stack

* GPU model
* GPU architecture
* GPU memory
* driver version
* CUDA compatibility/runtime information
* compute capability where obtainable
* PCIe generation
* PCIe width
* current PCIe link state
* maximum PCIe link state
* memory clock
* SM clock
* maximum clocks
* power limit
* default power limit
* temperature limits
* memory type where discoverable
* ECC state
* persistence mode
* MIG state
* BAR1 information where relevant

Redact:

* GPU UUID
* serial numbers
* board serials
* MAC addresses
* hostname
* IP addresses

Public reports need hardware specifications, not unique device identifiers.

---

# 9. Deployment Configuration Discovery

This is extremely important.

Every benchmark must capture the **exact serving configuration** used for the deployment.

Inspect the machine using read-only mechanisms such as:

* process command line
* `/proc/<pid>/cmdline`
* `ps`
* Docker inspect
* Podman inspect
* container image metadata
* systemd unit configuration
* process environment where safe
* server endpoints
* `/metrics`
* engine version
* image digest
* Git revision if available

For vLLM, capture applicable configuration such as:

* model
* model revision
* quantization
* dtype
* KV cache dtype
* max model length
* GPU memory utilization
* max number of sequences
* max batched tokens
* tensor parallel setting
* prefix caching
* chunked prefill
* speculative decoding configuration
* MTP configuration
* attention backend
* enforce eager
* async scheduling
* compilation/cudagraph options
* scheduler configuration
* served model name
* tokenizer
* generation config
* all command-line arguments
* relevant environment variables
* vLLM version
* container image/tag/digest

For llama.cpp capture applicable options such as:

* model/GGUF
* quantization
* context size
* parallel slots
* batch size
* ubatch size
* GPU layers
* flash attention
* KV cache K type
* KV cache V type
* speculative decoding
* draft model
* MTP settings if applicable
* tensor placement
* mmap/no-mmap
* mlock
* CPU threads
* sampling configuration
* server version/build
* Git commit
* startup arguments

Store both:

1. structured normalized fields
2. sanitized original startup command

Every configuration item should become available as report metadata/tags.

---

# 10. Secret Sanitization

This repository is intended to be publishable.

Build a centralized sanitizer.

Sanitize BEFORE writing to disk.

Never write secrets and then attempt to clean them later.

Redact:

* IPv4 addresses
* IPv6 addresses
* hostnames
* usernames
* home-directory paths
* API keys
* authorization headers
* bearer tokens
* SSH credentials
* passwords
* tokens
* environment secrets
* URLs containing credentials
* GPU UUIDs
* serial numbers
* MAC addresses
* internal DNS names

Environment variables with names containing patterns such as:

```text
KEY
TOKEN
SECRET
PASSWORD
PASS
AUTH
CREDENTIAL
COOKIE
SESSION
```

must be considered sensitive unless explicitly allowlisted.

Create aggressive unit tests proving sanitization works.

A public report should refer to targets with aliases such as:

```text
gpu-host-01
benchmark-client
```

rather than actual infrastructure identities.

---

# 11. Benchmark Philosophy

This is not one "tokens per second" test.

Performance must be characterized across a multidimensional workload space.

The primary matrix is:

```text
INPUT CONTEXT
      ×
OUTPUT LENGTH
      ×
CONCURRENCY
      ×
CACHE STATE
      ×
LOAD CHARACTERISTIC
```

Every individual measurement cell must be identifiable.

Example:

```text
ISL=8192
OSL=512
concurrency=4
cache=cold
load=closed_loop
```

---

# 12. Input Context Matrix

Automatically determine the deployment's usable context limit.

Test representative prompt lengths.

Potential default sequence:

```text
128
512
1K
2K
4K
8K
16K
32K
64K
128K
256K
512K
```

Only include values supported by the deployment.

Also include near-limit measurements where useful:

```text
75% of max context
90% of max context
```

while leaving sufficient room for output tokens.

Deduplicate approximately equivalent points.

Do not send requests that intentionally exceed the valid context window unless running a specific boundary test.

Record both:

```text
target input tokens
actual input tokens
```

---

# 13. Output-Length Matrix

Test multiple output lengths where possible.

Example baseline matrix:

```text
32
128
256
512
1024
2048
```

Heavy mode may test additional values.

Track:

```text
target OSL
actual OSL
finish reason
EOS occurrence
truncation
```

Use engine-specific features such as `ignore_eos` only when safe and supported.

Do not silently pretend an output contained 1024 tokens when the model emitted 311.

---

# 14. Tokenizer Accuracy

Prompt lengths must be based on actual token counts rather than character-count approximations.

Attempt tokenizer discovery using:

1. explicit `--tokenizer`
2. detected model metadata
3. local tokenizer cache
4. compatible Hugging Face tokenizer
5. engine-specific tokenizer information

Create deterministic synthetic benchmark prompts at or extremely close to requested token lengths.

Record actual token counts returned by the server when available.

If tokenizer certainty is insufficient, flag the run accordingly.

---

# 15. Concurrency Matrix

Concurrency is one of the most important dimensions.

Start at:

```text
1
```

and dynamically scale:

```text
1
2
4
8
16
32
64
...
```

Do not blindly continue forever.

Detect the saturation knee using metrics such as:

* throughput gain
* TTFT degradation
* P95/P99 latency
* queue growth
* error rate
* GPU utilization
* KV cache pressure
* memory pressure

Allow:

```bash
--max-concurrency
```

The benchmark should identify:

* best single-stream performance
* scaling efficiency
* throughput saturation point
* latency knee
* maximum stable concurrency
* overload point where applicable

---

# 16. Closed-Loop and Open-Loop Load

At minimum implement closed-loop concurrency testing.

In closed-loop mode, each worker issues another request after completing its previous request.

Heavy mode should also be capable of open-loop/request-rate testing where useful.

Support load patterns such as:

```text
constant
poisson
```

where practical.

Do not make this requirement unnecessarily complicated for the first implementation, but architect workload generation so these modes can coexist.

---

# 17. Cold Cache vs Warm Cache

Both must be measured.

## Cold / low-reuse workload

Generate unique prompts or prefixes that minimize reusable KV-prefix cache.

Measure baseline behavior.

## Warm / prefix-cache workload

Use repeated shared prefixes and controlled prompt reuse.

Measure:

* TTFT improvement
* prefill throughput improvement
* cache hit rate if available
* effective throughput improvement
* power/energy difference
* concurrency behavior

Label every test:

```text
cache_mode=cold
cache_mode=warm
```

Never combine them into an unlabeled aggregate.

---

# 18. Core Client-Side Metrics

Calculate core metrics independently from streaming responses whenever possible.

At minimum collect:

## Latency

* request latency
* time to first byte where meaningful
* Time To First Token, TTFT
* Time To Second Token, TTST
* Time Per Output Token, TPOT
* Inter Token Latency, ITL
* decode duration
* prefill duration where derivable
* end-to-end latency

## Throughput

* prompt tokens/sec
* prefill tokens/sec
* decode tokens/sec
* generated/output tokens/sec
* total tokens/sec
* output tokens/sec per user
* requests/sec
* total completed requests
* goodput where an SLO is defined

## Sequence data

* input sequence length
* output sequence length
* total sequence length

## Errors

* HTTP error rate
* timeout rate
* malformed stream rate
* incomplete stream rate
* context overflow
* cancelled request rate
* truncated output rate

Use statistical summaries:

```text
count
mean
median
stddev
coefficient of variation
min
max
p50
p75
p90
p95
p99
p99.9 where sample size supports it
```

Do not report meaningless percentiles from tiny samples without labeling the limitation.

---

# 19. Network Measurements

Measure benchmark-client-to-server network effects.

Where possible collect:

* connection time
* DNS time if applicable
* TCP RTT estimate
* HTTP send time
* HTTP wait time
* receive time
* connection reuse
* bytes sent
* bytes received

Support network calibration so reports can distinguish:

```text
observed TTFT
estimated network contribution
network-adjusted TTFT
```

Do not silently subtract network latency without preserving the original observed number.

---

# 20. Server-Side Metrics

If `/metrics` or another Prometheus endpoint is available, automatically discover and collect it.

Do not require Prometheus itself.

Directly scrape the metrics endpoint.

Implement engine-specific mappings into a canonical schema.

For vLLM, capture available metrics including:

* TTFT
* inter-token latency
* request latency
* queue time
* prefill time
* decode time
* prompt-token throughput
* generation-token throughput
* running requests
* waiting requests
* KV-cache utilization
* cache metrics
* request success/error statistics

For llama.cpp, capture available server metrics such as:

* prompt tokens
* prompt processing time
* prompt throughput
* predicted/generated tokens
* generation processing time
* generation throughput
* processing requests
* deferred requests
* observed context high-water mark

But:

**Never assume an engine metric is correct solely because it exists.**

Compare it with independently calculated client-side measurements.

Record discrepancies.

---

# 21. GPU Telemetry

Collect everything safely available from the GPU.

Prefer:

1. DCGM
2. NVML
3. nvidia-smi
4. supplementary OS data

The collectors must gracefully degrade if a tool is unavailable.

Do not fail an otherwise valid benchmark simply because DCGM is absent.

Collect time-series telemetry during every benchmark cell.

Useful metrics include:

## Utilization

* GPU utilization
* SM activity
* Tensor Core activity where supported
* DRAM activity
* memory-controller utilization
* encoder/decoder utilization if relevant

## Memory

* VRAM allocated
* VRAM used
* VRAM free
* peak VRAM
* memory bandwidth activity
* BAR1 where useful

## Clocks

* SM clock
* graphics clock
* memory clock
* effective clocks where available
* maximum clocks
* clock throttling state

## Power

* instantaneous power
* average power
* min power
* max power
* configured power limit
* total energy consumed

## Thermals

* GPU temperature
* memory temperature where supported
* thermal limits
* thermal throttling state

## PCIe

* PCIe generation
* link width
* RX throughput
* TX throughput

## Health

* XID events
* ECC errors
* PCIe replay events
* power slowdown
* thermal slowdown
* reliability slowdown
* board-limit slowdown
* other clock-throttle reasons available from DCGM/NVML

Sample frequently enough to be useful without meaningfully disturbing inference.

Approximately one-second telemetry is a reasonable starting point, while allowing configuration.

Store the raw time series.

---

# 22. Efficiency Metrics

Calculate:

```text
output tokens / joule
total tokens / joule
joules / output token
joules / total token
joules / request
output tokens/sec/watt
requests/sec/watt
goodput/watt
average watts
peak watts
total benchmark energy
```

If electricity price is provided:

```bash
--power-cost-per-kwh 0.12
```

also calculate:

* estimated cost per million output tokens
* estimated cost per million total tokens
* estimated requests per kWh
* estimated tokens per kWh

Clearly label these as GPU-energy estimates unless whole-system power is actually being measured.

---

# 23. Benchmark Integrity

The suite must actively determine whether a benchmark can be trusted.

Before each run, inspect:

* unexpected GPU processes
* existing GPU utilization
* existing VRAM consumption
* thermals
* clocks
* power
* throttling
* ECC state
* XID events
* available memory
* benchmark-client CPU load
* network connectivity

During the run detect:

* GPU thermal throttling
* power throttling
* unexpected clock changes
* another process using the GPU
* GPU memory pressure
* OOM
* server restart
* HTTP failures
* dropped connections
* large network instability
* client-side load generator saturation
* measurement instability
* excessive variance

Every benchmark cell receives an integrity state:

```text
VALID
VALID_WITH_WARNINGS
INVALID
```

and machine-readable reason codes.

Examples:

```text
THERMAL_THROTTLING
POWER_THROTTLING
EXTERNAL_GPU_PROCESS
GPU_OOM
SERVER_RESTART
NETWORK_UNSTABLE
LOAD_GENERATOR_SATURATED
INSUFFICIENT_SAMPLES
OUTPUT_LENGTH_MISMATCH
HIGH_VARIANCE
METRIC_SOURCE_DISAGREEMENT
```

Do not quietly discard bad measurements.

Preserve them and clearly mark them invalid.

---

# 24. Warmup and Statistical Stability

Implement proper warmup.

Do not include initial model warmup behavior in steady-state numbers unless explicitly reported as cold-start behavior.

For steady-state benchmark cells:

1. warm up
2. execute measurement windows
3. evaluate variance
4. repeat when necessary
5. stop once sufficiently stable or the budget requires moving on

Heavy mode should use more repetitions and tighter confidence requirements.

Calculate confidence intervals where statistically meaningful.

Store every raw repetition.

Never keep only the final average.

---

# 25. Light and Heavy Modes Are Budget Policies

Do NOT build two fixed benchmark scripts.

Build a budget-aware benchmark planner.

## Light Mode

Intended duration:

```text
roughly 1-4 hours
```

Default:

```text
2 hours
```

unless overridden.

Example:

```bash
--mode light --budget 2h
```

Light mode should maximize information gained per unit of benchmark time.

Prioritize:

* baseline concurrency 1
* short context
* medium context
* long context
* representative output sizes
* cold/warm cache
* basic concurrency scaling
* saturation discovery
* core GPU telemetry
* power efficiency

Use early measurements to intelligently decide which cells are most valuable next.

## Heavy Mode

Intended duration:

```text
one or more days
```

Reasonable default:

```text
48h
```

but user-configurable.

Heavy mode should attempt comprehensive characterization:

* dense context matrix
* dense concurrency matrix
* multiple output lengths
* cold/warm cache
* more repetitions
* statistical confidence
* open-loop load where useful
* saturation characterization
* overload behavior
* stability testing
* soak testing
* power efficiency
* thermal behavior

The user can always override:

```bash
--budget 6h
--budget 24h
--budget 72h
```

The remaining budget should be visible during execution.

---

# 26. Adaptive Benchmark Planner

Build a planner that learns from completed measurements.

Do not waste six hours benchmarking obviously redundant regions.

Examples:

If concurrency:

```text
1 -> 2 -> 4 -> 8 -> 16
```

shows throughput plateauing at 8 and severe latency degradation at 16, focus additional samples around:

```text
6
8
10
12
```

rather than blindly running 32, 64, 128.

If context performance changes sharply between:

```text
32K
64K
```

add intermediate measurements.

If results are extremely stable, spend less budget repeating them.

If variance is high, allocate additional repetitions.

Persist planner decisions in:

```text
planner.jsonl
```

so the benchmark strategy itself is auditable.

---

# 27. Heavy-Mode Soak Testing

Heavy mode should reserve some budget for sustained stable load.

Possible duration should be budget-dependent.

Monitor over time:

* throughput drift
* TTFT drift
* decode speed drift
* memory growth
* VRAM growth
* host RAM growth
* GPU temperature
* clocks
* power
* error rates
* queue growth
* cache behavior
* server health

Identify whether performance degrades after sustained operation.

Generate time-series charts.

---

# 28. Canonical Data Model

Define a versioned benchmark schema.

Example:

```text
schema_version
benchmark_suite_version
scoring_version
```

Every measurement cell needs dimensions such as:

```json
{
  "model": "...",
  "engine": "vllm",
  "engine_version": "...",
  "gpu": "...",
  "quantization": "...",
  "input_tokens": 8192,
  "target_output_tokens": 512,
  "actual_output_tokens": 512,
  "concurrency": 4,
  "cache_mode": "cold",
  "load_mode": "closed_loop"
}
```

Then attach metrics and statistical distributions.

Use clear canonical units.

Prefer:

```text
milliseconds
seconds
tokens/sec
requests/sec
bytes
MiB/GiB
watts
joules
degrees Celsius
```

Avoid ambiguous unit names.

---

# 29. Repository Output Hierarchy

Use approximately:

```text
benchmarks/
└── <model-slug>/
    └── <YYYY-MM-DD>/
        └── <configuration-id>/
            └── <run-id>/
                ├── index.html
                ├── manifest.json
                ├── summary.json
                ├── metrics.csv
                ├── metrics.json
                ├── measurements.parquet
                ├── configuration.json
                ├── hardware.json
                ├── integrity.json
                ├── planner.jsonl
                ├── raw/
                ├── telemetry/
                ├── charts/
                └── logs/
```

The configuration ID should be deterministically derived from meaningful sanitized configuration fields.

Never include secrets or unique machine identifiers in the configuration hash.

The run ID should uniquely identify the individual execution.

---

# 30. Manifest

Every run MUST have:

```text
manifest.json
```

This is the authoritative index of the benchmark.

It should include:

* model
* model family
* model revision if known
* quantization
* parameter information where reliably known
* engine
* engine version
* engine startup flags
* normalized configuration
* GPU model
* GPU memory
* driver
* CUDA
* OS
* benchmark start/end
* benchmark duration
* benchmark mode
* budget
* workload dimensions tested
* configuration ID
* run ID
* benchmark suite version
* Git commit of benchmark suite
* Python version
* dependencies and versions
* tokenizer
* random seed
* telemetry sources
* server metrics sources
* optional AIPerf version
* integrity status
* list of generated artifacts
* tags

Everything important should be machine-readable.

---

# 31. Tags Everywhere

Tags are a major requirement.

Examples:

```text
model:qwen3.8-27b
engine:vllm
engine-version:x.y.z
gpu:rtx-5090
quant:q4_k_m
context:131072
kv-cache:fp8
prefix-cache:on
mtp:2
mode:light
date:2026-08-23
```

Automatically create tags from normalized configuration values.

Tags must power:

* report filters
* catalog filters
* site navigation
* comparison selection
* search

HTML pages should contain appropriate metadata/data attributes so filtering is straightforward.

---

# 32. Static Website

Keep the web layer simple.

No database server.

No React application unless absolutely necessary.

No required backend.

The entire repository should be servable using:

```bash
python -m http.server
```

or nginx, GitHub Pages, S3, etc.

Generate:

```text
site/index.html
```

plus model pages, configuration pages, and run pages.

Use static:

* HTML
* CSS
* JavaScript
* JSON
* Plotly

The static site should automatically rebuild after successful benchmark completion.

---

# 33. Visual Design

Use a clean GPU-engineering dashboard aesthetic inspired by NVIDIA hardware documentation.

Use approximately:

```text
green:      #76B900
dark gray:  #1E1E1E
white:      #FFFFFF
```

with additional neutral grays as needed.

Dark mode should be the primary presentation.

Do NOT:

* use the NVIDIA logo
* claim NVIDIA affiliation
* imply NVIDIA endorsement
* copy proprietary NVIDIA page layouts

The goal is:

> dark, technical, high-performance GPU dashboard with NVIDIA-green accents

not an imitation NVIDIA corporate website.

Reports should be dense enough for engineers but visually polished.

---

# 34. Run Report

Every run gets a polished:

```text
index.html
```

At the top provide an executive benchmark summary.

Example KPI cards:

```text
Model
GPU
Engine
Quantization
Max Context
Peak Decode TPS
Peak Prefill TPS
Best TTFT
Peak Aggregate TPS
Maximum Stable Concurrency
Peak VRAM
Average Power
Tokens/Joule
Integrity Status
```

Then sections:

1. Deployment Configuration
2. Hardware
3. Benchmark Matrix
4. Latency
5. Prefill
6. Decode
7. Throughput
8. Concurrency Scaling
9. Context Scaling
10. Cache Behavior
11. GPU Utilization
12. VRAM
13. Power & Energy Efficiency
14. Thermals
15. Stability
16. Benchmark Integrity
17. Raw Artifacts

---

# 35. Required Charts

Use Plotly.

Generate interactive charts and downloadable/static equivalents when practical.

At minimum include:

## Context scaling

```text
input length vs prefill TPS
input length vs TTFT
input length vs decode TPS
```

## Concurrency scaling

```text
concurrency vs aggregate output TPS
concurrency vs request throughput
concurrency vs TTFT
concurrency vs P95 latency
concurrency vs P99 latency
concurrency vs GPU utilization
concurrency vs power
```

## Cache

```text
cold vs warm TTFT
cold vs warm prefill TPS
cache hit rate vs performance
```

## Efficiency

```text
throughput vs watts
tokens/joule vs concurrency
tokens/joule vs context size
```

## Telemetry

```text
GPU utilization over time
VRAM over time
power over time
temperature over time
SM clock over time
memory clock over time
```

---

# 36. Heatmaps / Matrices

The core report should contain matrix-style visualizations.

Examples:

### Aggregate output TPS

Rows:

```text
context length
```

Columns:

```text
concurrency
```

Cell:

```text
output tokens/sec
```

Also produce equivalent heatmaps for:

* TTFT
* P95 TTFT
* P99 TTFT
* decode TPS
* prefill TPS
* request throughput
* GPU utilization
* VRAM
* power
* tokens/joule

The user should be able to visually identify the operating sweet spot.

---

# 37. Model Summary Page

Each model gets a persistent model-level page.

Example:

```text
site/models/qwen3.8-27b/index.html
```

This is the model's **tuning history**.

Show every configuration benchmarked for that model.

Allow sorting/filtering by:

* date
* GPU
* engine
* quantization
* context
* KV-cache configuration
* speculative decoding
* MTP
* concurrency
* engine version
* tags

Provide comparison summaries such as:

```text
Fastest single-user configuration
Highest decode TPS
Highest prefill TPS
Highest aggregate throughput
Lowest TTFT
Best long-context configuration
Best energy efficiency
Maximum stable concurrency
```

---

# 38. Configuration Comparison / Tuning Summary

The parent process will eventually deploy many configurations.

This child benchmark repository should make those runs comparable.

For every model, generate a tuning comparison table:

```text
Configuration
Engine
Flags
Quant
Context
Peak Decode TPS
Peak Prefill TPS
Best TTFT
Peak Aggregate TPS
P95
P99
Max Stable Concurrency
Peak VRAM
Average Watts
Tokens/Joule
Integrity
```

Calculate percentage differences between configurations.

Do not call every difference a "regression."

Instead present:

```text
Configuration comparison
Delta from baseline
Delta from previous
Delta from best
```

Generate Pareto-frontier charts such as:

```text
throughput vs TTFT
throughput vs power
throughput vs VRAM
long-context throughput vs TTFT
```

Highlight non-dominated configurations.

---

# 39. Performance Scores

Do not create a model-quality score.

Quality is explicitly outside scope.

Create performance score families, for example:

```text
Latency Score
Throughput Score
Single-Stream Score
Concurrency Scaling Score
Long-Context Score
Cache Efficiency Score
Energy Efficiency Score
Stability Score
```

Optionally create:

```text
Balanced Performance Score
```

but it must be clearly documented.

All scoring formulas must:

* be versioned
* be documented
* preserve raw values
* explain normalization
* avoid hiding tradeoffs

A score is a convenience for comparison, not a replacement for measurements.

Store:

```text
scoring_version
```

in the manifest.

---

# 40. Global Catalog

Generate:

```text
site/index.html
```

as the master benchmark catalog.

It should allow users to filter/search every historical benchmark.

Useful filters:

```text
Model
GPU
Engine
Engine Version
Quantization
Context Size
Benchmark Date
Benchmark Mode
Configuration
Tags
Integrity
```

Useful sortable columns:

```text
Model
GPU
Engine
Quant
Context
Peak Decode TPS
Peak Prefill TPS
TTFT
Peak Aggregate TPS
Max Stable Concurrency
Average Power
Tokens/Joule
Date
```

Clicking a row opens that benchmark report.

This should feel like a public hardware/model benchmarking database, while remaining completely static.

---

# 41. Machine-Readable Outputs

HTML is not enough.

Preserve:

```text
JSON
CSV
Parquet
JSONL
```

where appropriate.

Raw request-level timings and telemetry must remain available for future analysis.

Use tidy/long-form datasets where practical.

The static HTML report must always be regeneratable from the machine-readable data.

Do not make HTML the source of truth.

---

# 42. Resume / Checkpointing

This is mandatory.

Heavy benchmarks may run for days.

After every completed benchmark cell:

1. write results
2. fsync/flush important files
3. update run state
4. update planner state

If the program crashes, reboots, loses network connectivity, or is interrupted:

```bash
llmbench run ... --resume
```

should continue from the last safely completed unit.

Never repeat days of completed work unnecessarily.

Maintain:

```text
state.json
```

using atomic writes.

---

# 43. Reproducibility

Store everything required to understand and reproduce a benchmark.

Include:

* benchmark suite Git commit
* package versions
* Python version
* OS
* engine version
* engine flags
* model revision
* quantization
* tokenizer
* GPU
* driver
* CUDA
* seed
* benchmark settings
* planner decisions
* target workload dimensions
* actual workload dimensions
* raw timings
* environment metadata
* sanitized CLI
* telemetry collection configuration

Use SHA-256 hashes for relevant benchmark input files/artifacts.

Do not hash and publish secrets.

---

# 44. Synthetic Data by Default

Because this repository may be public:

Use synthetic prompts by default.

Do not accidentally benchmark or persist private production prompts.

If custom input is eventually supported, default to:

```text
do not persist prompt contents
```

unless an explicit opt-in flag allows it.

Store hashes and statistical metadata instead.

---

# 45. Benchmark Metadata Must Be Immutable

Once a run completes, treat its raw result directory as immutable.

If reports need improvements later, regenerate presentation files from raw data without changing the original measurement records.

Record:

```text
measurement_schema_version
report_generator_version
```

separately.

---

# 46. Optional AIPerf Integration

Research current AIPerf APIs and CLI.

If available, optionally allow:

```bash
--aiperf auto
--aiperf on
--aiperf off
```

Archive AIPerf outputs under:

```text
raw/aiperf/
```

Map useful AIPerf metrics into the canonical schema.

Compare AIPerf results against our native measurements.

Do not fail if AIPerf is unavailable.

Do not treat deprecated GenAI-Perf as the preferred implementation.

---

# 47. Engine-Native Cross Validation

Where available compare:

```text
client measurement
vs
engine metric
vs
AIPerf
```

Example:

```text
decode_tps.client = 87.3
decode_tps.vllm = 86.9
decode_tps.aiperf = 87.1
```

Calculate discrepancy percentages.

If sources differ materially, flag:

```text
METRIC_SOURCE_DISAGREEMENT
```

and show it in the report.

This is especially important because engine metrics may change or regress between software versions.

---

# 48. CLI User Experience

The CLI should be clear.

Examples:

```bash
llmbench inspect \
  --target http://host:8000/v1
```

Shows what would be benchmarked without running a benchmark.

```bash
llmbench plan \
  --target http://host:8000/v1 \
  --mode light \
  --budget 2h
```

Shows the initial proposed benchmark plan.

```bash
llmbench run \
  --target http://host:8000/v1 \
  --mode light \
  --budget 2h
```

Runs.

```bash
llmbench run \
  --target http://host:8000/v1 \
  --mode heavy \
  --budget 48h \
  --resume
```

Runs/resumes heavy mode.

```bash
llmbench report <run-directory>
```

Regenerates report.

```bash
llmbench site build
```

Rebuilds global static website.

```bash
llmbench compare <run1> <run2>
```

Produces direct comparison.

---

# 49. Parent-Orchestrator Contract

Remember that another program will invoke this program later.

Make the child easy to automate.

Exit codes should distinguish:

```text
success
success-with-warnings
invalid benchmark
configuration/connection error
runtime failure
```

At completion write:

```text
run_result.json
```

containing:

```json
{
  "status": "success",
  "run_id": "...",
  "configuration_id": "...",
  "manifest": "...",
  "report": "...",
  "integrity": "VALID",
  "summary_metrics": {}
}
```

The parent should not need to parse terminal text.

---

# 50. Suggested Project Architecture

Use a maintainable Python project.

Something approximately like:

```text
llmbench/
├── pyproject.toml
├── README.md
├── src/
│   └── llmbench/
│       ├── cli/
│       ├── benchmark/
│       ├── planner/
│       ├── workloads/
│       ├── metrics/
│       ├── telemetry/
│       ├── discovery/
│       ├── adapters/
│       │   ├── base.py
│       │   ├── vllm.py
│       │   └── llamacpp.py
│       ├── integrity/
│       ├── storage/
│       ├── schemas/
│       ├── scoring/
│       ├── reports/
│       ├── site/
│       └── security/
├── templates/
├── static/
├── tests/
├── docs/
└── examples/
```

Use sensible separation of concerns.

---

# 51. Testing

This requires serious automated testing.

Include unit tests for:

* token timing
* TTFT calculation
* ITL calculation
* TPOT
* throughput
* percentiles
* energy calculations
* score calculations
* configuration hashing
* sanitization
* engine detection
* manifest generation
* resume state
* planner behavior
* HTML generation
* schema validation

Build a mock OpenAI-compatible streaming server for integration tests.

Simulate:

* normal streaming
* delayed first token
* slow decode
* truncated output
* HTTP failure
* timeout
* malformed SSE
* server restart
* context overflow

Tests must run without requiring a GPU.

GPU integration tests can be optional.

---

# 52. Documentation

Produce:

```text
README.md
docs/architecture.md
docs/benchmark-methodology.md
docs/benchmark-methodology-sources.md
docs/metrics.md
docs/scoring.md
docs/telemetry.md
docs/security-redaction.md
docs/engine-adapters.md
docs/report-schema.md
docs/parent-integration.md
docs/troubleshooting.md
```

README should contain copy/paste examples.

---

# 53. Implementation Priorities

Build in this order:

## Phase 1

* project skeleton
* schemas
* OpenAI streaming client
* basic benchmark executor
* TTFT/ITL/TPOT/throughput
* dynamic target
* checkpointing

## Phase 2

* GPU/NVML/DCGM telemetry
* host introspection
* sanitization
* hardware manifest

## Phase 3

* vLLM adapter
* llama.cpp adapter
* configuration discovery
* Prometheus scraping

## Phase 4

* context/output/concurrency/cache matrix
* adaptive planner
* Light/Heavy budget system
* benchmark integrity

## Phase 5

* Plotly reports
* static website
* model/configuration comparisons
* tags/filtering

## Phase 6

* AIPerf integration
* metric cross-validation
* scoring
* soak tests
* documentation hardening

But do not leave the repository at Phase 1.

Continue through a functional end-to-end implementation.

---

# 54. Important Engineering Constraints

Favor:

* deterministic behavior
* type hints
* dataclasses/Pydantic where appropriate
* atomic file writes
* bounded memory use
* async HTTP for concurrency
* streaming token timing
* clear logging
* structured errors
* reproducible outputs
* schema versioning
* testability

Avoid:

* giant monolithic scripts
* brittle regex parsing without fallbacks
* hard-coded hostnames
* hard-coded GPU models
* hard-coded context windows
* hard-coded engine versions
* writing credentials
* modifying the deployment
* silently throwing away failed benchmark cells

---

# 55. Definition of Done

The implementation is not done until I can point it at a running vLLM or llama.cpp OpenAI-compatible server and execute:

```bash
llmbench run \
  --target http://TARGET:PORT/v1 \
  --mode light \
  --budget 2h
```

and receive a directory containing:

```text
manifest.json
configuration.json
hardware.json
summary.json
metrics.csv
metrics.json
measurements.parquet
raw measurement data
GPU telemetry
integrity results
interactive HTML report
charts
logs
```

and the static site automatically contains the new benchmark.

I should then be able to change the model's deployment configuration externally and rerun the benchmark.

The site should recognize it as another configuration of the same model and show both configurations in the model's tuning history.

I should be able to compare them using:

* raw metrics
* matrices
* charts
* scores
* percentage deltas
* Pareto frontiers
* tags
* filters

without manually editing files.

---

# 56. Final Instruction

Start by inspecting the existing repository and environment.

Then perform the benchmark-methodology research.

Then write the architecture/schema documentation needed to keep the implementation coherent.

Then implement the system.

Do not merely tell me how it could be built.

Do not ask me to manually collect configuration information that can be discovered automatically.

Do not redeploy or alter the model.

Do not optimize the deployment.

Do not benchmark model quality.

Build the child benchmarking system that accepts a dynamically specified OpenAI-compatible endpoint, comprehensively characterizes the performance of that exact single-GPU deployment, captures its exact configuration and hardware state, preserves the raw data, produces polished static reports, and adds the result to a permanent searchable historical benchmark catalog.

Proceed.
