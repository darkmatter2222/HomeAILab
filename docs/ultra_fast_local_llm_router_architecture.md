# Ultra-Fast Local LLM Router
## Architecture, Manifest, Routing Rules, Port Contracts, and Deployment Standard

**Status:** Proposed reference architecture  
**Primary clients:** Claude Code and OpenAI-compatible clients  
**Inference runtimes:** llama.cpp, vLLM, SGLang  
**Deployment platform:** Docker / Portainer  
**Primary design goals:** deterministic routing, millisecond-class router overhead, static capacity control, automatic endpoint discovery, strict compatibility enforcement, and easy expansion to additional GPU hosts.

---

# 1. Executive Summary

This architecture defines a lightweight local inference router that sits between clients such as Claude Code and a fleet of heterogeneous GPU inference servers.

The router must not perform slow health checks, model introspection, GPU polling, or capacity queries in the request hot path.

Instead, the system is divided into two planes:

1. **Control Plane**
   - Discovers candidate endpoints.
   - Performs health checks.
   - Reads or validates endpoint manifests.
   - Validates port contracts.
   - Builds endpoint capability signatures.
   - Enables or disables endpoints.
   - Maintains the in-memory routing table.

2. **Data Plane**
   - Receives OpenAI-compatible requests.
   - Determines request requirements.
   - Selects an already-approved endpoint from an in-memory routing table.
   - Reserves one static capacity slot atomically.
   - Proxies the request.
   - Streams the response.
   - Releases the slot when the request truly terminates.

The request path should contain no network calls other than the selected inference request itself.

---

# 2. Core Design Principles

## 2.1 Hosts are configured; endpoints are discovered

The administrator should configure only:

- Host IP or hostname.
- Allowed runtime port ranges.
- Static instance capacity overrides when necessary.
- Host priority.
- Optional host labels.

The router discovers individual inference endpoints inside the reserved ranges.

Example:

```yaml
hosts:
  - name: rtx5090
    address: 192.168.86.20
    priority: 10

  - name: rtx3090
    address: 192.168.86.21
    priority: 20

  - name: dgx-spark
    address: 192.168.86.30
    priority: 30
```

The router should not require every model endpoint to be manually entered.

---

## 2.2 Port ranges are permanent infrastructure contracts

Recommended permanent allocation:

| Runtime / Service | Port Range | Purpose |
|---|---:|---|
| Router API | 8000-8009 | Router ingress and administrative API |
| llama.cpp | 8100-8199 | llama.cpp model instances |
| vLLM | 8200-8299 | vLLM model instances |
| SGLang | 8300-8399 | SGLang model instances |
| Vision-specialized endpoints | 8400-8499 | Optional dedicated VLM range |
| Embeddings / rerankers | 8500-8599 | Optional embedding/reranker services |
| Metrics / exporters | 9000-9099 | Prometheus-compatible metrics |
| Management | 9100-9199 | Optional router/admin sidecars |

A runtime appearing outside its assigned port range must not enter the routing table.

Example:

- llama.cpp on port `8112` -> valid.
- llama.cpp on port `8220` -> rejected.
- vLLM on port `8241` -> valid.
- SGLang on port `8155` -> rejected.

This must be enforced by the router, not merely documented.

---

# 3. High-Level Architecture

```mermaid
flowchart LR
    CC[Claude Code]
    API[Other OpenAI-Compatible Clients]

    R[LLM Router<br/>Data Plane]
    RT[(In-Memory<br/>Routing Table)]

    CP[Router Control Plane]
    D[Discovery Scanner]
    H[Health Monitor]
    V[Manifest + Signature Validator]

    N5090[RTX 5090 Host]
    N3090[RTX 3090 Host]
    DGX[DGX Spark Host]
    FUTURE[Future GPU Hosts]

    CC -->|OpenAI API| R
    API -->|OpenAI API| R

    R <--> RT

    CP --> RT
    D --> CP
    H --> CP
    V --> CP

    D -. scan reserved ports .-> N5090
    D -. scan reserved ports .-> N3090
    D -. scan reserved ports .-> DGX
    D -. scan reserved ports .-> FUTURE

    R -->|selected request only| N5090
    R -->|selected request only| N3090
    R -->|selected request only| DGX
    R -->|selected request only| FUTURE
```

---

# 4. Control Plane vs Data Plane

## 4.1 Control Plane

The control plane operates asynchronously.

Responsibilities:

- Port discovery.
- Health checks.
- Model manifest retrieval.
- Runtime detection.
- Signature calculation.
- Compatibility validation.
- Static capacity assignment.
- Endpoint enable/disable.
- Endpoint recovery.
- Updating the routing table.

The control plane may operate every few seconds because it does not block individual inference requests.

Suggested intervals:

```yaml
control_plane:
  discovery_interval_ms: 5000
  health_interval_ms: 2000
  failure_threshold: 2
  recovery_threshold: 2
```

These values may later be tuned.

---

## 4.2 Data Plane

The data plane is the latency-sensitive path.

It should perform only:

```text
Request arrives
    |
    v
Parse request metadata
    |
    v
Determine request capability signature
    |
    v
Read in-memory compatible endpoint list
    |
    v
Select endpoint
    |
    v
Atomic capacity reservation
    |
    v
Proxy request
    |
    v
Stream result
    |
    v
Release reservation
```

No endpoint health probe should occur here.

No GPU utilization check should occur here.

No Prometheus query should occur here.

No runtime `/metrics` query should occur here.

No model metadata API should occur here.

---

# 5. Router Hot-Path Diagram

```mermaid
sequenceDiagram
    participant C as Claude Code
    participant R as Router
    participant T as In-Memory Routing Table
    participant E as Selected Endpoint

    C->>R: POST /v1/messages or /v1/chat/completions
    R->>R: Inspect request requirements
    R->>T: Lookup compatible candidates
    T-->>R: Pre-ranked endpoint list
    R->>R: Atomically reserve capacity slot
    R->>E: Forward request immediately
    E-->>R: Streaming tokens
    R-->>C: Streaming tokens

    Note over R,E: No health check or GPU polling in request path

    E-->>R: Stream completes / disconnect / error
    R->>R: Atomically release capacity slot
```

---

# 6. Endpoint Manifest

Every model deployment should expose or otherwise provide a manifest describing its immutable and semi-static characteristics.

Recommended endpoint:

```text
GET /.well-known/llm-router-manifest
```

Alternative:

```text
GET /router/manifest
```

The manifest may be served directly by the inference container or by a tiny sidecar.

---

# 7. Canonical Endpoint Manifest Schema

```yaml
schema_version: "1.0"

instance:
  id: "rtx5090-qwen38-262k-01"
  display_name: "RTX5090 Qwen3.8 27B 262K"
  enabled: true

host:
  name: "rtx5090"
  address: "192.168.86.20"
  gpu_class: "RTX_5090"
  gpu_count: 1

runtime:
  type: "llama.cpp"
  version: "build-or-version-string"
  api_family: "openai"
  port: 8101

model:
  canonical_name: "Qwen3.8-27B"
  served_model_name: "qwen3.8-27b"
  architecture: "qwen"
  quantization: "NVFP4"
  model_hash: "optional-sha256-or-build-id"

capabilities:
  text: true
  vision: false
  tools: true
  streaming: true
  reasoning: true
  embeddings: false

context:
  max_context_tokens: 262144
  max_output_tokens: 16384

request_format:
  chat_template_id: "qwen3.8"
  tokenizer_id: "Qwen/Qwen3.8-27B"
  tool_schema: "openai"
  image_schema: "none"

behavior:
  thinking_mode: false
  supports_temperature: true
  supports_top_p: true
  supports_seed: true

routing:
  static_capacity: 1
  priority: 10
  pool: "coding"
  context_class: "262k"

observability:
  health_path: "/health"
  models_path: "/v1/models"
  metrics_path: "/metrics"
```

---

# 8. Endpoint Signature

The router must calculate a normalized compatibility signature.

An endpoint should not be eligible unless its signature satisfies the request.

Recommended signature fields:

```yaml
signature:
  api_family: openai
  model_family: qwen3.8
  tokenizer_id: Qwen/Qwen3.8-27B
  chat_template_id: qwen3.8
  tool_schema: openai
  supports_tools: true
  supports_streaming: true
  supports_vision: false
  max_context_tokens: 262144
  max_output_tokens: 16384
  thinking_mode: false
```

---

# 9. Hard Signature vs Soft Attributes

Not every endpoint property should be treated identically.

## 9.1 Hard compatibility fields

A mismatch excludes the endpoint.

Recommended hard fields:

- API family.
- Model family when exact family consistency is required.
- Tokenizer.
- Chat template.
- Tool-call schema.
- Vision support.
- Streaming support.
- Minimum context requirement.
- Minimum output-token requirement.
- Required reasoning mode.
- Required image-input format.

## 9.2 Soft routing attributes

These affect ranking but do not necessarily disqualify an endpoint.

Examples:

- Host priority.
- GPU type.
- Quantization.
- Context class.
- Static capacity.
- Preferred runtime.
- Preferred model.
- Performance tier.

---

# 10. Signature Enforcement Example

Claude Code sends a normal text coding request.

Request requirement:

```yaml
request_signature:
  requires_text: true
  requires_vision: false
  requires_tools: true
  requires_streaming: true
  estimated_context_tokens: 41000
  requested_output_tokens: 12000
```

Potential endpoints:

```text
5090 / 262K / tools / text       -> MATCH
5090 / 64K  / tools / text       -> MATCH
3090 / 131K / tools / text       -> MATCH
DGX  / 64K  / tools / vision     -> MATCH, but lower priority
DGX  / 32K  / tools / text       -> REJECT: context too small
DGX  / 262K / no tools / text    -> REJECT: tools unsupported
```

The router then ranks only the compatible endpoints.

---

# 11. Context Window Handling

Claude Code should not be assumed to explicitly request an endpoint with a specific context class.

Therefore the router should make decisions from observed request size.

The router can estimate:

```text
input tokens
+ requested output allowance
+ safety reserve
= required context
```

Example:

```text
41,000 input tokens
+ 16,384 output allowance
+ 4,096 routing reserve
= 61,480 required tokens
```

This request fits a 64K instance.

---

# 12. Context Routing Classes

Recommended classes:

```yaml
context_classes:
  - name: "64k"
    minimum: 0
    maximum: 65536

  - name: "131k"
    minimum: 65537
    maximum: 131072

  - name: "262k"
    minimum: 131073
    maximum: 262144
```

The router should choose the smallest compatible context class unless priority rules override it.

This preserves faster endpoints for small requests while preserving long-context nodes for requests that need them.

---

# 13. Optional Context Headroom

Do not route a request to an endpoint with effectively zero remaining context.

Recommended:

```yaml
context_policy:
  reserve_tokens: 4096
  reserve_percent: 0.05
```

Actual requirement:

```text
required_context =
input_tokens
+ max_output_tokens
+ max(4096, max_context * 5%)
```

This prevents boundary-condition failures.

---

# 14. Vision Routing

Image-containing requests should be classified before normal routing.

Example rule:

```yaml
vision_policy:
  require_vision_capability_when_image_present: true
  reject_text_only_endpoints: true
```

If a request contains an image:

```text
5090 text model     -> excluded
3090 text model     -> excluded
DGX text model      -> excluded
DGX VLM model       -> eligible
```

---

# 15. Example DGX Spark Layout

```text
DGX Spark
|
+-- Port 8301
|   SGLang
|   Large Text Model
|   Context: 131K
|   Capacity: 3
|
+-- Port 8401
    Vision-Language Model
    Context: 64K
    Capacity: 2
```

Both instances operate independently.

The router tracks separate capacities:

```yaml
dgx-spark-text:
  capacity: 3
  inflight: 2
  available: 1

dgx-spark-vlm:
  capacity: 2
  inflight: 1
  available: 1
```

---

# 16. Static Capacity Model

Capacity should be a router configuration value, not dynamically inferred from GPU utilization.

Example:

```yaml
instances:
  rtx5090-qwen262:
    capacity: 1

  rtx3090-qwen131:
    capacity: 1

  dgx-qwen131:
    capacity: 3

  dgx-vlm64:
    capacity: 2
```

The router may discover the endpoint dynamically but apply a capacity rule based on matching selectors.

Example:

```yaml
capacity_rules:
  - match:
      host: rtx5090
      port: 8101
    capacity: 1

  - match:
      host: dgx-spark
      port: 8301
    capacity: 3

  - match:
      host: dgx-spark
      port: 8401
    capacity: 2
```

---

# 17. Capacity State Machine

Each endpoint maintains:

```yaml
capacity_state:
  maximum: 3
  inflight: 1
  reserved: 0
  available: 2
```

A reservation must be atomic.

Conceptually:

```text
if inflight < capacity:
    inflight += 1
    assign request
else:
    try next endpoint
```

The comparison and increment must occur as one atomic operation.

---

# 18. When Capacity Is Released

Capacity must remain occupied until one of the following occurs:

- Streaming response completes normally.
- Upstream closes the connection.
- Client disconnects.
- Router timeout terminates the request.
- Upstream request errors.
- Cancellation propagates.

Do NOT free the capacity slot merely because HTTP response headers were received.

This is a likely cause of routing race conditions in poorly implemented proxies.

---

# 19. Capacity Lease Safety

To prevent leaked capacity after crashes or broken connections, give each reservation a lease.

Example:

```yaml
leases:
  enabled: true
  hard_timeout_seconds: 7200
```

Each active request record:

```yaml
request_id: "req_abc123"
endpoint_id: "dgx-qwen131"
started_at: "2026-08-30T11:00:00-04:00"
last_activity_at: "2026-08-30T11:05:31-04:00"
```

A watchdog can repair clearly orphaned reservations.

The watchdog is a control-plane activity and must not block routing.

---

# 20. Primary Routing Policy

Desired preference:

```text
RTX 5090
   ↓
RTX 3090
   ↓
DGX Spark
   ↓
Future hosts
```

But only among endpoints that satisfy the request signature.

---

# 21. Routing Algorithm

Recommended algorithm:

```text
1. Parse request.
2. Determine capabilities required.
3. Estimate context requirement.
4. Identify compatible endpoint pool.
5. Remove unhealthy/disabled endpoints.
6. Remove endpoints with insufficient static capacity.
7. Sort by routing priority.
8. Prefer smallest adequate context class.
9. Atomically reserve first candidate.
10. Proxy immediately.
11. If reservation race is lost, try next candidate.
12. If upstream fails before meaningful response, optionally fail over.
13. Release reservation on termination.
```

---

# 22. Candidate Scoring

A deterministic score can be used.

Example:

```text
score =
  host_priority
+ context_waste_penalty
+ runtime_preference
+ model_preference
```

Lower score wins.

Example weighting:

```yaml
routing_weights:
  host_priority: 1000
  context_waste: 10
  runtime_preference: 5
```

Or keep it simpler and use ordered filters.

For maximum predictability, ordered filters are preferable to complex adaptive scoring.

---

# 23. Recommended Deterministic Ranking

```text
FILTER:
  endpoint enabled
  endpoint healthy
  port contract valid
  model signature valid
  vision requirements valid
  tool requirements valid
  context large enough
  static capacity available

SORT:
  request-specific preferred pool
  host priority
  smallest sufficient context
  endpoint priority
```

---

# 24. Example Normal Text Request

Request:

```text
Text only
Tools required
52K total required context
```

Available:

```text
5090 64K  capacity free
5090 262K capacity free
3090 131K capacity free
DGX 131K capacity free
```

Result:

```text
5090 64K
```

If the 5090 64K endpoint is full:

```text
5090 262K
```

Or, depending on policy:

```text
3090 131K
```

The exact order should be explicitly configured.

---

# 25. Example Long-Context Request

Request:

```text
Text only
Tools required
170K required context
```

Candidates:

```text
5090 262K -> eligible
3090 131K -> rejected
DGX 131K  -> rejected
DGX VLM64 -> rejected
```

Only the 5090 262K deployment enters the candidate list.

---

# 26. Example Vision Request

Request contains image.

Candidates:

```text
5090 text 262K -> rejected
3090 text 131K -> rejected
DGX text 131K  -> rejected
DGX VLM 64K    -> eligible
```

Result:

```text
DGX VLM 64K
```

---

# 27. Portainer Deployment Standard

Every Portainer stack should explicitly declare its host port.

Example llama.cpp stack:

```yaml
services:
  model:
    image: ghcr.io/example/llama-cpp:latest
    container_name: llama-qwen-5090-01

    ports:
      - "${LLM_PORT}:8080"

    environment:
      ROUTER_RUNTIME: "llama.cpp"
      ROUTER_PORT: "${LLM_PORT}"
      ROUTER_MODEL: "Qwen3.8-27B"
      ROUTER_CONTEXT: "262144"
      ROUTER_CAPACITY: "1"
```

Portainer environment:

```env
LLM_PORT=8101
```

---

# 28. Port Contract Validation in Deployment

A deployment wrapper or CI check should validate:

```text
llama.cpp -> 8100-8199
vLLM      -> 8200-8299
SGLang    -> 8300-8399
VLM       -> 8400-8499
```

Invalid configuration should fail deployment when possible.

Example pseudo-validation:

```text
runtime == llama.cpp AND port not in 8100..8199 => FAIL
runtime == vllm      AND port not in 8200..8299 => FAIL
runtime == sglang    AND port not in 8300..8399 => FAIL
```

The router repeats this validation on discovery.

This gives two enforcement layers.

---

# 29. Portainer Naming Standard

Recommended:

```text
<runtime>-<model>-<host>-<context>-<instance>
```

Examples:

```text
llamacpp-qwen38-5090-262k-01
vllm-qwen38-3090-131k-01
sglang-qwen38-dgxspark-131k-01
sglang-qwen-vl-dgxspark-64k-01
```

---

# 30. Docker Labels

Every inference container should include router metadata as Docker labels.

Example:

```yaml
labels:
  ai.router.enabled: "true"
  ai.router.runtime: "llama.cpp"
  ai.router.model: "Qwen3.8-27B"
  ai.router.context: "262144"
  ai.router.vision: "false"
  ai.router.tools: "true"
  ai.router.capacity: "1"
  ai.router.signature: "qwen38-openai-tools-v1"
```

These are useful even if discovery occurs over the network.

---

# 31. Router Main Configuration

Example:

```yaml
router:
  listen:
    host: "0.0.0.0"
    port: 8000

  hot_path:
    perform_health_checks: false
    query_metrics: false
    query_gpu_state: false
    query_models_endpoint: false

  request:
    default_max_output_tokens: 16384
    context_reserve_tokens: 4096
    context_reserve_percent: 5

  retry:
    reservation_retries: 3
    upstream_connect_retries: 1
    retry_after_stream_started: false
```

---

# 32. Host Configuration

```yaml
hosts:
  - id: rtx5090
    address: 192.168.86.20
    priority: 10
    enabled: true

  - id: rtx3090
    address: 192.168.86.21
    priority: 20
    enabled: true

  - id: dgx-spark
    address: 192.168.86.30
    priority: 30
    enabled: true
```

---

# 33. Port Range Configuration

```yaml
port_contracts:
  llama.cpp:
    start: 8100
    end: 8199

  vllm:
    start: 8200
    end: 8299

  sglang:
    start: 8300
    end: 8399

  vision:
    start: 8400
    end: 8499
```

---

# 34. Discovery Configuration

```yaml
discovery:
  enabled: true
  interval_ms: 5000

  connect_timeout_ms: 250
  response_timeout_ms: 750

  scan:
    port_contracts:
      - llama.cpp
      - vllm
      - sglang
      - vision

  require_manifest: true
  reject_unknown_runtime: true
  reject_port_contract_violation: true
```

---

# 35. Health Monitoring

Health checks occur outside the request path.

Example:

```yaml
health:
  interval_ms: 2000
  timeout_ms: 750
  failure_threshold: 2
  recovery_threshold: 2

  acceptable_status:
    - 200
```

State:

```text
UNKNOWN
  ↓
HEALTHY
  ↓ failures
SUSPECT
  ↓ threshold reached
UNHEALTHY
  ↓ recovery checks
HEALTHY
```

---

# 36. Endpoint Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Discovered
    Discovered --> Validating
    Validating --> Rejected: invalid manifest or port
    Validating --> Healthy: valid + health passes

    Healthy --> Suspect: health failure
    Suspect --> Healthy: recovery
    Suspect --> Unhealthy: failure threshold

    Unhealthy --> Healthy: recovery threshold
    Healthy --> Draining: admin drain
    Draining --> Disabled: inflight reaches zero
    Disabled --> Healthy: admin enable
```

---

# 37. Graceful Draining

The router must support draining an endpoint.

Example:

```text
POST /admin/endpoints/{id}/drain
```

Drain behavior:

```text
Existing requests continue.
No new requests assigned.
When inflight == 0:
    endpoint becomes disabled.
```

This is important for replacing models without breaking Claude Code sessions.

---

# 38. In-Memory Routing Table

Suggested structure:

```yaml
endpoint_id: rtx5090-qwen38-262k-01

network:
  host: 192.168.86.20
  port: 8101
  base_url: http://192.168.86.20:8101

state:
  enabled: true
  healthy: true
  draining: false

routing:
  host_priority: 10
  endpoint_priority: 10
  pool: coding

capacity:
  max: 1
  inflight: 0

signature:
  model_family: qwen3.8
  api_family: openai
  tools: true
  vision: false
  streaming: true
  max_context: 262144
  max_output: 16384
  tokenizer: Qwen/Qwen3.8-27B
  template: qwen3.8
```

This object should already exist before a request arrives.

---

# 39. Fast Lookup Indexes

Do not scan every endpoint for every request once the cluster becomes larger.

Maintain indexes.

Example:

```text
pool:text+tools+64k
pool:text+tools+131k
pool:text+tools+262k
pool:vision+tools+64k
```

Or bitset-style capability indexes:

```text
vision endpoints
tool endpoints
streaming endpoints
64K+ endpoints
131K+ endpoints
262K+ endpoints
```

Candidate intersection can then be performed entirely in memory.

---

# 40. Request Classification

The router should derive:

```yaml
request:
  client: claude-code
  has_images: false
  requires_tools: true
  streaming: true
  input_token_estimate: 42000
  requested_max_output: 16384
  required_context: 62384
```

Claude Code does not need to explicitly know the target context pool.

The router makes that decision.

---

# 41. Token Counting

Best accuracy:

```text
Use the tokenizer matching the endpoint/model family.
```

Fast fallback:

```text
Approximate token count from request size.
```

Recommended architecture:

- Exact count when practical.
- Cached tokenizer instance.
- No external tokenizer service.
- Token calculation occurs locally in router memory/process.

If exact token counting becomes expensive, use a conservative fast estimate and a larger safety margin.

---

# 42. API Compatibility

The router should expose a stable external API even when the internal runtimes differ.

Recommended endpoints:

```text
GET  /v1/models
POST /v1/chat/completions
POST /v1/responses
POST /v1/messages            # optional Anthropic compatibility layer
GET  /health
GET  /metrics
```

Claude Code should point to the router, never directly to individual inference containers.

---

# 43. Stable Public Model Alias

The client-facing model name should not expose physical topology.

Example:

```text
local-coding
```

Router maps:

```text
local-coding
    |
    +-- 5090 Qwen3.8 64K
    +-- 5090 Qwen3.8 262K
    +-- 3090 Qwen3.8 131K
    +-- DGX Qwen3.8 131K
```

Vision alias:

```text
local-vision
```

Or allow automatic request-based vision selection behind one alias.

---

# 44. Model Signature Groups

Example:

```yaml
signature_groups:
  qwen38_coding:
    model_family: qwen3.8
    tokenizer: Qwen/Qwen3.8-27B
    chat_template: qwen3.8
    tool_schema: openai
    tools: true
    streaming: true
    thinking_mode: false

  qwen_vlm:
    model_family: qwen-vl
    tools: true
    streaming: true
    vision: true
```

Every discovered endpoint must match one approved group.

Unknown signatures are rejected by default.

---

# 45. Why Signature Enforcement Matters

Without signature enforcement:

```text
Request begins on endpoint A.
Later request is routed to endpoint B.
Endpoint B interprets tools differently.
Tool call fails.
Claude Code retries.
Router thinks capacity is exhausted.
Session appears randomly broken.
```

With signature enforcement:

```text
Only endpoints with compatible behavior are members of the same logical pool.
```

---

# 46. Failure Handling

Failures fall into separate categories.

## Before upstream response starts

Safe to retry another endpoint:

- Connection refused.
- TCP timeout.
- HTTP 502/503.
- Upstream immediately rejects request.
- Endpoint became unhealthy.

## After token streaming begins

Do not silently move the same generation to another endpoint.

The generation state is not transferable.

Return the error to the client unless a higher-level resumability mechanism exists.

---

# 47. Race Condition Prevention

Common failure:

```text
Request A checks capacity = free
Request B checks capacity = free
A assigns
B assigns
Both use same final slot
```

Correct:

```text
Atomic compare-and-increment
```

If reservation fails:

```text
Try next ranked endpoint.
```

No global router lock should be needed.

Use per-endpoint atomic counters or narrow locks.

---

# 48. Sticky Routing

Do not require session stickiness unless there is state that truly exists only on one backend.

For stateless OpenAI-style calls:

```text
Each request may be routed independently.
```

Optional affinity may improve prefix cache reuse.

Example:

```yaml
affinity:
  enabled: true
  key:
    - conversation_id
  strength: preferred
```

Important:

Affinity must be a preference, not a hard requirement, unless the inference runtime requires it.

---

# 49. Prefix Cache-Aware Optional Optimization

Later, the router may prefer a backend that recently handled the same conversation.

This can improve prompt-cache reuse.

But this should not involve querying cache state dynamically.

The router can maintain its own lightweight mapping:

```text
conversation abc -> endpoint rtx5090-qwen262
```

If compatible and capacity is available:

```text
reuse endpoint
```

Otherwise:

```text
fall through normally
```

---

# 50. Router Availability

Because Claude Code depends on the router, the router itself should be lightweight and stable.

Recommended:

```text
Router container
    |
    +-- read-only configuration
    +-- small persisted state only if needed
    +-- no heavyweight database required
```

Routing state can live entirely in memory and rebuild from discovery on restart.

---

# 51. Router Container Layout

```yaml
services:
  llm-router:
    image: local/llm-router:latest
    container_name: llm-router
    restart: unless-stopped

    ports:
      - "8000:8000"

    volumes:
      - ./config:/app/config:ro

    environment:
      ROUTER_CONFIG: /app/config/router.yaml
```

---

# 52. Router Internal Components

```mermaid
flowchart TB
    HTTP[HTTP / Streaming Proxy]
    CLASS[Request Classifier]
    TOKEN[Token Estimator]
    MATCH[Signature Matcher]
    SCHED[Deterministic Scheduler]
    CAP[Atomic Capacity Manager]
    TABLE[(Routing Table)]

    DISC[Discovery Worker]
    HEALTH[Health Worker]
    VALID[Manifest Validator]
    CONFIG[Configuration Loader]

    HTTP --> CLASS
    CLASS --> TOKEN
    TOKEN --> MATCH
    MATCH --> SCHED
    SCHED --> CAP
    CAP --> TABLE
    CAP --> HTTP

    DISC --> VALID
    HEALTH --> TABLE
    VALID --> TABLE
    CONFIG --> VALID
    CONFIG --> SCHED
```

---

# 53. No Database in the Hot Path

Avoid:

- Redis lookup per request.
- PostgreSQL lookup per request.
- Prometheus query per request.
- Docker API query per request.
- Portainer API query per request.

All routing data should be local memory.

Redis may be useful later for multi-router active-active coordination, but is unnecessary for one router instance.

---

# 54. Metrics

Router metrics should include:

```text
router_requests_total
router_requests_inflight
router_request_duration_seconds
router_route_selection_seconds
router_upstream_connect_seconds

router_endpoint_capacity
router_endpoint_inflight
router_endpoint_available

router_endpoint_healthy
router_endpoint_registered

router_route_rejections_total
router_context_rejections_total
router_signature_rejections_total
router_capacity_rejections_total

router_upstream_errors_total
router_client_disconnects_total
```

---

# 55. Important Debug Metrics

For diagnosing "no capacity" errors:

```text
endpoint capacity
endpoint inflight
request ID
selected endpoint
reason each other endpoint was rejected
reservation start
reservation release
stream completion
client disconnect
```

The router should be able to explain every routing decision.

---

# 56. Routing Decision Log

Example:

```json
{
  "request_id": "req_1234",
  "required_context": 58110,
  "vision": false,
  "tools": true,
  "selected": "rtx5090-qwen64-01",
  "candidates": [
    {
      "id": "rtx5090-qwen64-01",
      "result": "selected"
    },
    {
      "id": "rtx5090-qwen262-01",
      "result": "eligible-lower-rank"
    },
    {
      "id": "rtx3090-qwen131-01",
      "result": "eligible-lower-rank"
    },
    {
      "id": "dgx-vlm64-01",
      "result": "eligible-but-vision-reserved"
    }
  ]
}
```

---

# 57. Rejection Reason Codes

Use explicit internal reason codes:

```text
PORT_CONTRACT_MISMATCH
MANIFEST_INVALID
MODEL_SIGNATURE_MISMATCH
VISION_REQUIRED
TOOLS_REQUIRED
STREAMING_REQUIRED
CONTEXT_TOO_SMALL
OUTPUT_LIMIT_TOO_SMALL
ENDPOINT_UNHEALTHY
ENDPOINT_DISABLED
ENDPOINT_DRAINING
CAPACITY_FULL
RESERVATION_RACE_LOST
UPSTREAM_CONNECT_FAILED
```

This makes debugging dramatically easier.

---

# 58. Admin API

Recommended:

```text
GET  /admin/hosts
GET  /admin/endpoints
GET  /admin/routing-table
GET  /admin/requests
GET  /admin/config

POST /admin/discovery/rescan
POST /admin/endpoints/{id}/enable
POST /admin/endpoints/{id}/disable
POST /admin/endpoints/{id}/drain
POST /admin/endpoints/{id}/undrain
```

Optional:

```text
POST /admin/config/reload
```

---

# 59. Router Status Output

Example:

```text
HOST        ENDPOINT               PORT  CTX   CAP  USED  HEALTH  PRIORITY
5090        qwen38-64k             8101  64K   1    0     UP      10
5090        qwen38-262k            8102  262K  1    1     UP      10
3090        qwen38-131k            8101  131K  1    0     UP      20
DGX Spark   qwen38-131k            8301  131K  3    2     UP      30
DGX Spark   qwen-vlm-64k           8401  64K   2    0     UP      30
```

---

# 60. Recommended Network Layout

```mermaid
flowchart LR
    CLIENTS[Claude Code / VS Code / Scripts]

    ROUTER[Router<br/>192.168.86.x:8000]

    H5090[RTX 5090<br/>192.168.86.20]
    H3090[RTX 3090<br/>192.168.86.21]
    HDGX[DGX Spark<br/>192.168.86.30]

    L1[8101 llama.cpp 64K]
    L2[8102 llama.cpp 262K]

    L3[8101 llama.cpp 131K]

    S1[8301 SGLang Text 131K]
    V1[8401 VLM 64K]

    CLIENTS --> ROUTER

    ROUTER --> H5090
    ROUTER --> H3090
    ROUTER --> HDGX

    H5090 --> L1
    H5090 --> L2

    H3090 --> L3

    HDGX --> S1
    HDGX --> V1
```

---

# 61. Full Request Decision Tree

```mermaid
flowchart TD
    A[Request Arrives]
    B{Contains image?}
    C[Require vision]
    D[Text route]
    E[Determine tool requirement]
    F[Estimate required context]
    G[Lookup matching signature pool]
    H[Remove unhealthy / draining]
    I[Remove insufficient context]
    J[Remove capacity-full endpoints]
    K{Candidates remain?}
    L[Sort by priority + context class]
    M[Atomic reservation]
    N{Reservation won?}
    O[Proxy immediately]
    P[Try next candidate]
    Q[Return capacity / compatibility error]
    R[Stream response]
    S[Release capacity]

    A --> B
    B -- Yes --> C
    B -- No --> D
    C --> E
    D --> E
    E --> F
    F --> G
    G --> H
    H --> I
    I --> J
    J --> K
    K -- No --> Q
    K -- Yes --> L
    L --> M
    M --> N
    N -- No --> P
    P --> M
    N -- Yes --> O
    O --> R
    R --> S
```

---

# 62. Recommended Router Configuration File

```yaml
version: "1"

router:
  bind: "0.0.0.0"
  port: 8000

  public_model_aliases:
    coding: "local-coding"
    vision: "local-vision"

hosts:
  - id: rtx5090
    address: 192.168.86.20
    priority: 10

  - id: rtx3090
    address: 192.168.86.21
    priority: 20

  - id: dgx-spark
    address: 192.168.86.30
    priority: 30

port_contracts:
  llama.cpp:
    range: [8100, 8199]

  vllm:
    range: [8200, 8299]

  sglang:
    range: [8300, 8399]

  vision:
    range: [8400, 8499]

discovery:
  interval_ms: 5000
  connect_timeout_ms: 250
  response_timeout_ms: 750
  require_manifest: true
  reject_unknown_endpoints: true

health:
  interval_ms: 2000
  timeout_ms: 750
  failure_threshold: 2
  recovery_threshold: 2

context:
  reserve_tokens: 4096
  reserve_percent: 5

routing:
  strategy: deterministic

  host_order:
    - rtx5090
    - rtx3090
    - dgx-spark

  prefer_smallest_sufficient_context: true
  query_dynamic_gpu_capacity: false
  query_dynamic_runtime_capacity: false
  health_check_in_request_path: false

capacity_rules:
  - match:
      host: rtx5090
      port: 8101
    capacity: 1

  - match:
      host: rtx5090
      port: 8102
    capacity: 1

  - match:
      host: rtx3090
      port: 8101
    capacity: 1

  - match:
      host: dgx-spark
      port: 8301
    capacity: 3

  - match:
      host: dgx-spark
      port: 8401
    capacity: 2

signature_groups:
  coding_qwen38:
    api_family: openai
    model_family: qwen3.8
    tokenizer_id: Qwen/Qwen3.8-27B
    chat_template_id: qwen3.8
    tool_schema: openai
    tools: true
    streaming: true
    thinking_mode: false

  vision_qwen:
    api_family: openai
    vision: true
    tools: true
    streaming: true

leases:
  enabled: true
  hard_timeout_seconds: 7200

affinity:
  enabled: true
  mode: preferred
  allow_fallback: true

logging:
  routing_decisions: true
  rejected_candidates: true
```

---

# 63. Endpoint Manifest Example: RTX 5090

```yaml
schema_version: "1.0"

instance:
  id: rtx5090-qwen38-262k-01

host:
  name: rtx5090
  address: 192.168.86.20
  gpu_class: RTX_5090

runtime:
  type: llama.cpp
  port: 8102
  api_family: openai

model:
  canonical_name: Qwen3.8-27B
  served_model_name: qwen3.8-27b
  quantization: NVFP4

capabilities:
  text: true
  vision: false
  tools: true
  streaming: true
  reasoning: true

context:
  max_context_tokens: 262144
  max_output_tokens: 16384

request_format:
  tokenizer_id: Qwen/Qwen3.8-27B
  chat_template_id: qwen3.8
  tool_schema: openai

behavior:
  thinking_mode: false

routing:
  static_capacity: 1
  priority: 10
  pool: coding
```

---

# 64. Endpoint Manifest Example: DGX Vision Model

```yaml
schema_version: "1.0"

instance:
  id: dgx-vlm-64k-01

host:
  name: dgx-spark
  address: 192.168.86.30
  gpu_class: GB10

runtime:
  type: sglang
  port: 8401
  api_family: openai

model:
  canonical_name: Qwen-VL
  served_model_name: local-vision

capabilities:
  text: true
  vision: true
  tools: true
  streaming: true

context:
  max_context_tokens: 65536
  max_output_tokens: 8192

request_format:
  tokenizer_id: qwen-vl-tokenizer
  chat_template_id: qwen-vl
  tool_schema: openai
  image_schema: openai-content-array

routing:
  static_capacity: 2
  priority: 30
  pool: vision
```

---

# 65. Future Host Expansion

Adding a new GPU should require approximately:

```yaml
hosts:
  - id: rtx-pro-6000-01
    address: 192.168.86.40
    priority: 15
```

Then deploy models inside approved port ranges.

The control plane discovers them.

No router source-code modification should be required.

---

# 66. Future Multiple Models Per Host

Supported naturally.

Example:

```text
RTX PRO 6000 Host
|
+-- 8101 llama.cpp Qwen 64K
+-- 8102 llama.cpp Qwen 262K
+-- 8201 vLLM DeepSeek 131K
+-- 8301 SGLang coding model
+-- 8401 SGLang VLM
```

Each port is an independent schedulable endpoint.

---

# 67. Runtime Independence

The router should not fundamentally care whether the backend is:

- llama.cpp.
- vLLM.
- SGLang.
- TensorRT-LLM.
- Another OpenAI-compatible runtime.

Runtime is mainly used for:

- Port contract.
- Health adapter.
- Manifest validation.
- Optional API translation.
- Observability.

Routing should operate on normalized endpoint signatures.

---

# 68. Security Boundary

Router should preferably be accessible only from trusted LAN clients.

Inference endpoint ports should preferably be accessible only from:

- Router host.
- Administrative network.
- Monitoring systems when required.

Conceptual firewall:

```text
Claude Code
   |
   v
Router :8000
   |
   +----> inference networks

Direct client -> inference endpoint
    BLOCK unless explicitly needed
```

This prevents accidental bypass of routing rules.

---

# 69. Startup Behavior

Router startup:

```text
1. Load configuration.
2. Build empty routing table.
3. Launch HTTP listener.
4. Launch discovery worker.
5. Scan configured hosts / port contracts.
6. Validate manifests.
7. Perform health validation.
8. Add qualified endpoints.
9. Begin normal routing.
```

The API may return a clear `NO_ENDPOINTS_READY` message during initial discovery.

---

# 70. Router Restart

Because the routing table is rebuildable:

```text
Router restarts
    |
    v
Config reload
    |
    v
Discovery
    |
    v
Routing table reconstructed
```

No heavyweight persisted state is required.

Optional persistence can retain:

- Last-known endpoint metadata.
- Conversation affinity hints.
- Historical metrics.

But it must not be necessary for correctness.

---

# 71. Recommended Technology Stack

For the router itself:

```text
Language:
  Go or Rust preferred for extremely low overhead and predictable concurrency.

Alternative:
  Python/FastAPI can work but is less ideal if the goal is minimum router overhead.

Proxy:
  Native streaming HTTP client/server.

State:
  In-process memory.

Metrics:
  Prometheus endpoint.

Configuration:
  YAML.

Deployment:
  Docker container through Portainer.
```

Go is a particularly strong fit for this design because of:

- Very low proxy overhead.
- Simple concurrency.
- Atomic counters.
- Mature HTTP stack.
- Single binary deployment.
- Excellent streaming support.
- Easy Prometheus integration.

---

# 72. What the Router Must Never Do on Every Request

Do not:

```text
query nvidia-smi
query Prometheus
query /metrics
query /health
query /v1/models
query Docker
query Portainer
scan ports
benchmark the model
ask runtime current queue length
recalculate endpoint manifest
```

Those belong in the control plane.

---

# 73. What the Router May Do on Every Request

Allowed hot-path operations:

```text
parse JSON
detect image content
read requested model
estimate/count tokens
calculate required context
in-memory signature lookup
in-memory sorting / pre-ranked list
atomic capacity reservation
HTTP proxy
stream bytes/tokens
atomic capacity release
```

---

# 74. Target Router Overhead

The exact result depends on implementation and network topology, but the architectural target should be:

```text
Routing decision:
sub-millisecond to low-single-digit milliseconds

Router-added local latency before upstream connect:
as close to negligible as practical

No periodic health interval should affect request acceptance.
```

The inference server's own TTFT will dominate.

---

# 75. Why the Current "No Capacity" Failure Can Happen

Potential causes this architecture explicitly prevents:

1. Capacity checked remotely and data becomes stale.
2. Health and capacity are conflated.
3. Request slot released too early.
4. Request slot never released after disconnect.
5. Multiple requests race for the same slot.
6. Router counts retries as separate persistent sessions.
7. Router treats inactive but healthy endpoint as unavailable.
8. Router polls slower than request arrival rate.
9. Different context endpoints are incorrectly grouped.
10. Client retries after an upstream error while original capacity remains leaked.

---

# 76. Reliability Requirements

The finished router should pass at least these tests:

```text
[ ] 100 simultaneous routing decisions do not exceed static capacity.
[ ] Client disconnect releases capacity.
[ ] Upstream disconnect releases capacity.
[ ] Router timeout releases capacity.
[ ] Failed reservation retries another endpoint.
[ ] Unhealthy endpoint disappears from hot routing table.
[ ] Recovered endpoint automatically returns.
[ ] Wrong runtime/port combination is rejected.
[ ] Wrong tokenizer signature is rejected.
[ ] Wrong tool schema is rejected.
[ ] Vision request never reaches text-only model.
[ ] Oversized context request never reaches smaller endpoint.
[ ] Drain removes endpoint from new scheduling.
[ ] Existing stream survives endpoint drain.
[ ] Router restart rebuilds state automatically.
```

---

# 77. Recommended Load Tests

Test categories:

### Routing latency

```text
10,000 synthetic requests against mocked inference servers.
Measure router decision latency.
```

### Capacity correctness

```text
Capacity = 1
Launch 100 simultaneous requests.
Exactly one should reserve the endpoint.
```

### Multi-endpoint failover

```text
5090 full
3090 free
DGX free

New request must route to 3090.
```

### Vision isolation

```text
Image request
Only VLM pool is eligible.
```

### Context boundary

```text
63K -> 64K valid
66K -> 64K rejected
66K -> 131K valid
140K -> 131K rejected
140K -> 262K valid
```

---

# 78. Recommended Administrative UX

A small status page is useful.

Example:

```text
LOCAL AI ROUTER

RTX 5090
  Qwen 64K       UP    0/1
  Qwen 262K      UP    1/1

RTX 3090
  Qwen 131K      UP    0/1

DGX Spark
  Qwen 131K      UP    2/3
  Qwen Vision    UP    0/2
```

Each endpoint can show:

- Status.
- Current capacity.
- Context.
- Runtime.
- Port.
- Model signature.
- Drain button.
- Recent routing decisions.

---

# 79. Deployment Folder Layout

Recommended repository:

```text
llm-router/
|
+-- router/
|   +-- cmd/
|   +-- internal/
|   |   +-- api/
|   |   +-- proxy/
|   |   +-- routing/
|   |   +-- capacity/
|   |   +-- discovery/
|   |   +-- health/
|   |   +-- manifest/
|   |   +-- tokenizer/
|   |   +-- metrics/
|   |   +-- config/
|   |
|   +-- Dockerfile
|
+-- config/
|   +-- router.yaml
|   +-- signature-groups.yaml
|   +-- capacity-rules.yaml
|
+-- deployments/
|   +-- router/
|   |   +-- docker-compose.yaml
|   |
|   +-- templates/
|       +-- llamacpp-stack.yaml
|       +-- vllm-stack.yaml
|       +-- sglang-stack.yaml
|       +-- vlm-stack.yaml
|
+-- docs/
|   +-- ARCHITECTURE.md
|   +-- PORTS.md
|   +-- MANIFEST.md
|   +-- OPERATIONS.md
|
+-- tests/
    +-- routing/
    +-- capacity/
    +-- discovery/
    +-- failover/
    +-- compatibility/
```

---

# 80. Port Allocation Registry

Keep one human-readable registry in source control.

```yaml
allocations:
  rtx5090:
    8101:
      name: qwen38-64k
      runtime: llama.cpp

    8102:
      name: qwen38-262k
      runtime: llama.cpp

  rtx3090:
    8101:
      name: qwen38-131k
      runtime: llama.cpp

  dgx-spark:
    8301:
      name: qwen38-131k
      runtime: sglang

    8401:
      name: qwen-vlm-64k
      runtime: sglang
```

The router should not require this file for discovery, but it is useful for operators and Portainer deployment hygiene.

---

# 81. Final Recommended Logical Topology

```mermaid
flowchart TB
    CLAUDE[Claude Code]
    ROUTER[Ultra-Fast AI Router]

    subgraph ROUTER_INTERNAL[Router]
        CLASSIFY[Request Classification]
        INDEX[Precomputed Capability Index]
        CAPACITY[Atomic Static Capacity]
        PROXY[Streaming Proxy]
        CONTROL[Async Discovery + Health]
    end

    subgraph HOST1[RTX 5090]
        A1[64K Coding<br/>llama.cpp :8101]
        A2[262K Coding<br/>llama.cpp :8102]
    end

    subgraph HOST2[RTX 3090]
        B1[131K Coding<br/>llama.cpp :8101]
    end

    subgraph HOST3[DGX Spark]
        C1[131K Coding<br/>SGLang :8301<br/>Capacity 3]
        C2[64K Vision<br/>SGLang :8401<br/>Capacity 2]
    end

    CLAUDE --> ROUTER
    ROUTER --> CLASSIFY
    CLASSIFY --> INDEX
    INDEX --> CAPACITY
    CAPACITY --> PROXY

    CONTROL -. maintains .-> INDEX
    CONTROL -. maintains .-> CAPACITY

    PROXY --> A1
    PROXY --> A2
    PROXY --> B1
    PROXY --> C1
    PROXY --> C2
```

---

# 82. Final Operational Rules

1. **Clients talk only to the router.**
2. **Inference runtimes live only inside their assigned port contracts.**
3. **Hosts are configured; model endpoints are discovered.**
4. **Every endpoint must have a validated manifest/signature.**
5. **Unknown or incompatible endpoints are rejected.**
6. **Health checking is asynchronous.**
7. **No health check occurs in the inference request hot path.**
8. **Capacity is defined statically by router policy.**
9. **Capacity is never inferred from momentary GPU utilization.**
10. **Reservations are atomic.**
11. **Capacity remains consumed until the stream actually terminates.**
12. **Context compatibility is enforced before routing.**
13. **Vision requests can only enter vision-capable pools.**
14. **Host preference is deterministic: 5090 -> 3090 -> DGX unless a request capability requires otherwise.**
15. **The router should prefer the smallest sufficient context deployment when appropriate.**
16. **The same logical pool must use compatible tokenizer, template, tools, and API behavior.**
17. **Portainer deployments must follow permanent runtime port assignments.**
18. **Draining is used before model removal/redeployment.**
19. **Every routing rejection must have an explicit reason code.**
20. **Adding another GPU host should normally require only adding the host and deploying compliant containers.**

---

# 83. Recommended First Implementation

Build the first version with only:

```text
OpenAI-compatible ingress
Static host configuration
Port-range discovery
Manifest validation
Async health checks
In-memory endpoint registry
Static capacity rules
Atomic reservation
Context enforcement
Vision enforcement
Deterministic host priority
Streaming proxy
Prometheus metrics
Routing-decision logs
Drain / enable / disable API
```

Do not initially add:

```text
dynamic GPU utilization scheduling
machine-learning scheduling
Prometheus-driven scheduling
distributed consensus
Redis
complex queue prediction
automatic model loading
dynamic batching control
runtime queue probing
```

Those increase complexity and are unnecessary for the stated objective.

---

# 84. Design Objective

The router should behave less like a GPU monitoring system and more like a very fast Layer-7 scheduler with model-awareness.

The basic mental model is:

```text
DISCOVER SLOWLY
VALIDATE STRICTLY
STORE LOCALLY
ROUTE IMMEDIATELY
COUNT ATOMICALLY
STREAM DIRECTLY
```

That separation is the central architectural decision.

It allows the environment to grow from three GPU systems to many hosts and many model deployments without turning each Claude Code request into a distributed health-and-capacity investigation.
