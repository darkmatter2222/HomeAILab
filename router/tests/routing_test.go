package tests

import (
	"testing"

	"llm-router/internal/manifest"
	"llm-router/internal/registry"
	"llm-router/internal/routing"
)

// buildTable builds a registry with 5090 (262K, prio 10) + a hypothetical
// 3090 (131K, prio 20) to verify deterministic ordering + context filtering.
func buildTable(t *testing.T) *registry.Table {
	eps := []manifest.Endpoint{
		{
			ID: "rtx5090-qwen38-262k-01",
			Enabled: true,
			Host: manifest.Host{Name: "rtx5090", Address: "192.168.86.37", Priority: 10},
			Runtime: manifest.Runtime{Type: "vllm", APIFamily: "openai", Port: 8201},
			Model:   manifest.Model{ServedModelName: "qwen3.8"},
			Capabilities: manifest.Capabilities{Text: true, Tools: true, Streaming: true},
			Context:   manifest.Context{MaxContextTokens: 262144, ContextClass: "262k"},
			Routing:   manifest.RoutingPolicy{StaticCapacity: 1, Priority: 10},
		},
		{
			ID: "rtx3090-qwen38-131k-01",
			Enabled: true,
			Host: manifest.Host{Name: "rtx3090", Address: "192.168.86.40", Priority: 20},
			Runtime: manifest.Runtime{Type: "llama.cpp", APIFamily: "openai", Port: 8101},
			Model:   manifest.Model{ServedModelName: "qwen3.8"},
			Capabilities: manifest.Capabilities{Text: true, Tools: true, Streaming: true},
			Context:   manifest.Context{MaxContextTokens: 131072, ContextClass: "131k"},
			Routing:   manifest.RoutingPolicy{StaticCapacity: 1, Priority: 20},
		},
	}
	return registry.NewTable(eps, nil)
}

// TestDeterministicOrder: small request prefers the 5090 (priority 10).
func TestDeterministicOrderPrefers5090(t *testing.T) {
	tbl := buildTable(t)
	req := routing.Req{RequiresTools: true, InputTokenEstimate: 100, RequestedMaxOutput: 100}
	reqCtx := routing.RequiredContext(req.InputTokenEstimate, req.RequestedMaxOutput, 4096, 5, 400)
	out := routing.Select(tbl, req, reqCtx, nil, "lease1")
	if out.Selected == nil {
		t.Fatal("no endpoint selected")
	}
	if out.Selected.Manifest.ID != "rtx5090-qwen38-262k-01" {
		t.Fatalf("expected 5090 (priority 10) selected, got %s", out.Selected.Manifest.ID)
	}
	if !out.Reserved {
		t.Fatal("expected a reservation")
	}
}

// TestContextTooSmallExcludesSmallEndpoint: a 200K-context request must not
// route to the 131K endpoint.
func TestContextTooSmallExcludesSmallEndpoint(t *testing.T) {
	tbl := buildTable(t)
	// Force the request to need >131072 context.
	req := routing.Req{InputTokenEstimate: 200000, RequestedMaxOutput: 16384, RequiresTools: true}
	reqCtx := routing.RequiredContext(req.InputTokenEstimate, req.RequestedMaxOutput, 4096, 5, 1000000)
	if reqCtx <= 131072 {
		t.Fatalf("test setup: reqCtx %d should exceed 131072", reqCtx)
	}
	out := routing.Select(tbl, req, reqCtx, nil, "lease2")
	if out.Selected == nil {
		t.Fatal("no endpoint selected for 200K request")
	}
	if out.Selected.Manifest.Context.MaxContextTokens < reqCtx {
		t.Fatalf("selected endpoint context %d < required %d", out.Selected.Manifest.Context.MaxContextTokens, reqCtx)
	}
	// 3090 (131K) must be rejected with CONTEXT_TOO_SMALL.
	found3090 := false
	for _, c := range out.Candidates {
		if c.ID == "rtx3090-qwen38-131k-01" && c.Result == string(routing.ReasonContextTooSmall) {
			found3090 = true
		}
	}
	if !found3090 {
		t.Fatalf("expected 3090 rejected with CONTEXT_TOO_SMALL, got candidates %+v", out.Candidates)
	}
}

// TestVisionFilter: an image request excludes the text-only 5090/3090 endpoints.
func TestVisionRequestExcludedFromTextEndpoints(t *testing.T) {
	tbl := buildTable(t)
	req := routing.Req{HasImages: true, RequiresTools: true, InputTokenEstimate: 100}
	out := routing.Select(tbl, req, 1000, nil, "lease3")
	if out.Selected != nil {
		t.Fatalf("expected no selection (no vision endpoint), got %s", out.Selected.Manifest.ID)
	}
	// Every candidate should be VISION_REQUIRED.
	for _, c := range out.Candidates {
		if c.Result != string(routing.ReasonVisionRequired) {
			t.Fatalf("expected VISION_REQUIRED for %s, got %s", c.ID, c.Result)
		}
	}
}
