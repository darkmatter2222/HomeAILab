// Package manifest defines the endpoint identity contract: what a
// schedulable inference endpoint claims about itself (capabilities, context,
// model, runtime, port). The control plane validates these claims; the hot
// data plane reads the resulting signatures from the routing table without
// ever re-querying the upstream.
package manifest

import "fmt"

// Capabilities are the hard routing dimensions a request can require.
type Capabilities struct {
	Text      bool `json:"text" yaml:"text"`
	Vision    bool `json:"vision" yaml:"vision"`
	Tools     bool `json:"tools" yaml:"tools"`
	Streaming bool `json:"streaming" yaml:"streaming"`
	Reasoning bool `json:"reasoning" yaml:"reasoning"`
	Embeddings bool `json:"embeddings" yaml:"embeddings"`
}

// Context declares the token budget the endpoint can serve.
type Context struct {
	MaxContextTokens int    `json:"max_context_tokens" yaml:"max_context_tokens"`
	ContextClass     string `json:"context_class" yaml:"context_class"` // "64k" | "131k" | "262k"
	MaxOutputTokens  int    `json:"max_output_tokens" yaml:"max_output_tokens"`
}

// Model identity.
type Model struct {
	CanonicalName   string `json:"canonical_name" yaml:"canonical_name"`
	ServedModelName string `json:"served_model_name" yaml:"served_model_name"`
	Quantization    string `json:"quantization" yaml:"quantization"`
}

// Runtime describes the serving engine and its published port.
type Runtime struct {
	Type      string `json:"type" yaml:"type"` // vllm | llama.cpp | sglang | ...
	Version   string `json:"version" yaml:"version"`
	APIFamily string `json:"api_family" yaml:"api_family"` // openai | anthropic | ...
	Port      int    `json:"port" yaml:"port"`             // host-facing published port
}

// Behavior pins request/translation semantics that must be identical for a
// conversation to stay consistent across an endpoint.
type Behavior struct {
	Thinking           bool   `json:"thinking" yaml:"thinking"`
	ToolSchema         string `json:"tool_schema" yaml:"tool_schema"`
	ToolCallParser     string `json:"tool_call_parser" yaml:"tool_call_parser"`
	ReasoningParser    string `json:"reasoning_parser" yaml:"reasoning_parser"`
	ChatTemplatePolicy string `json:"chat_template_policy" yaml:"chat_template_policy"`
}

// RoutingPolicy is the static scheduling contract.
type RoutingPolicy struct {
	Pool            string `json:"pool" yaml:"pool"`
	StaticCapacity  int    `json:"static_capacity" yaml:"static_capacity"`
	Priority        int    `json:"priority" yaml:"priority"` // lower = more preferred
	SignatureGroup  string `json:"signature_group" yaml:"signature_group"`
}

// HealthPaths for the async health worker.
type HealthPaths struct {
	Path string `json:"path" yaml:"path"`
}

// Endpoint is the declarative identity of one schedulable inference instance.
// Seeded statically (config/endpoints) and/or discovered. The router never
// treats this as mutable in the hot path; the registry owns live state.
type Endpoint struct {
	ID         string       `json:"id" yaml:"id"`
	Enabled    bool         `json:"enabled" yaml:"enabled"`
	Host       Host         `json:"host" yaml:"host"`
	Runtime    Runtime      `json:"runtime" yaml:"runtime"`
	Model      Model        `json:"model" yaml:"model"`
	Capabilities Capabilities `json:"capabilities" yaml:"capabilities"`
	Context    Context      `json:"context" yaml:"context"`
	Behavior   Behavior     `json:"behavior" yaml:"behavior"`
	Routing    RoutingPolicy `json:"routing" yaml:"routing"`
	Health     HealthPaths  `json:"health" yaml:"health"`
	Models     HealthPaths  `json:"models" yaml:"models"`
	Metrics    HealthPaths  `json:"metrics" yaml:"metrics"`
}

// Host is the physical placement of the endpoint.
type Host struct {
	Name     string `json:"name" yaml:"name"`
	Address  string `json:"address" yaml:"address"`
	GPUClass string `json:"gpu_class" yaml:"gpu_class"`
	Priority int    `json:"priority" yaml:"priority"`
}

// Signature is the normalized compatibility fingerprint the router computes
// from an endpoint. Requests are matched against signatures, not raw
// endpoints, so incompatible backends can never silently share a pool.
type Signature struct {
	APIFamily      string
	ModelFamily    string
	Tokenizer      string
	ChatTemplate   string
	ToolSchema     string
	ToolCallParser string
	SupportsTools  bool
	SupportsVision bool
	SupportsStream bool
	MaxContext     int
	MaxOutput      int
	ThinkingMode   bool
}

// SignatureFromEndpoint derives the hard compatibility fields. Soft fields
// (runtime version, quantization, GPU class) intentionally do not appear —
// they affect ranking, not eligibility.
func SignatureFromEndpoint(e *Endpoint) Signature {
	return Signature{
		APIFamily:      e.Runtime.APIFamily,
		ModelFamily:    e.Model.ServedModelName,
		Tokenizer:      e.Behavior.ChatTemplatePolicy,
		ChatTemplate:   e.Behavior.ChatTemplatePolicy,
		ToolSchema:     e.Behavior.ToolSchema,
		ToolCallParser: e.Behavior.ToolCallParser,
		SupportsTools:  e.Capabilities.Tools,
		SupportsVision: e.Capabilities.Vision,
		SupportsStream: e.Capabilities.Streaming,
		MaxContext:     e.Context.MaxContextTokens,
		MaxOutput:      e.Context.MaxOutputTokens,
		ThinkingMode:   e.Behavior.Thinking,
	}
}

// PortContract is a runtime->port-range rule. An endpoint whose published port
// falls outside its runtime's range is a configuration error and is excluded.
type PortContract struct {
	Runtime string
	Start   int
	End     int
}

// InRange reports whether p is within the contract's range.
func (c PortContract) InRange(p int) bool { return p >= c.Start && p <= c.End }

// ValidatePortContract enforces the permanent port ranges. It returns a
// descriptive error when the endpoint's port is outside its runtime's
// contract (or when the runtime is unknown). A nil/empty contract list means
// enforcement is disabled (returns nil).
func ValidatePortContract(e *Endpoint, contracts []PortContract) error {
	if len(contracts) == 0 {
		return nil
	}
	for _, c := range contracts {
		if c.Runtime != e.Runtime.Type {
			continue
		}
		if !c.InRange(e.Runtime.Port) {
			return fmt.Errorf("PORT_CONTRACT_MISMATCH: %s runtime port %d outside %s range [%d-%d]",
				e.Runtime.Type, e.Runtime.Port, c.Runtime, c.Start, c.End)
		}
		return nil // found a matching runtime contract and it passed
	}
	return fmt.Errorf("PORT_CONTRACT_MISMATCH: no port contract for runtime %q", e.Runtime.Type)
}

// Manifest is the on-wire shape a runtime may serve at
// /.well-known/llm-router-manifest. Discovery (control plane) may fetch it to
// enrich a seed or discover a new endpoint; the data plane never reads it.
type Manifest struct {
	SchemaVersion string    `json:"schema_version" yaml:"schema_version"`
	Instance      Instance  `json:"instance" yaml:"instance"`
	Host          Host      `json:"host" yaml:"host"`
	Runtime       Runtime   `json:"runtime" yaml:"runtime"`
	Model         Model     `json:"model" yaml:"model"`
	Capabilities  Capabilities `json:"capabilities" yaml:"capabilities"`
	Context       Context   `json:"context" yaml:"context"`
	Behavior      Behavior  `json:"behavior" yaml:"behavior"`
	Routing       RoutingPolicy `json:"routing" yaml:"routing"`
	Health        HealthPaths `json:"health" yaml:"health"`
}

// Instance identity for a manifest.
type Instance struct {
	ID         string `json:"id" yaml:"id"`
	DisplayName string `json:"display_name" yaml:"display_name"`
	Enabled    bool   `json:"enabled" yaml:"enabled"`
}

// ToEndpoint converts a discovered manifest into a seedable Endpoint.
func (m Manifest) ToEndpoint() Endpoint {
	e := Endpoint{
		ID:           m.Instance.ID,
		Enabled:      m.Instance.Enabled,
		Host:         m.Host,
		Runtime:      m.Runtime,
		Model:        m.Model,
		Capabilities: m.Capabilities,
		Context:      m.Context,
		Behavior:     m.Behavior,
		Routing:      m.Routing,
		Health:       m.Health,
	}
	return e
}
