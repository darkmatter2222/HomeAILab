package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"llm-router/internal/api"
	"llm-router/internal/config"
	"llm-router/internal/manifest"
	"llm-router/internal/proxy"
	"llm-router/internal/registry"
	"llm-router/internal/telemetry"
)

// TestModelsAdvertisesAlias: /v1/models must advertise the public alias and
// the backend served name.
func TestModelsAdvertisesAlias(t *testing.T) {
	cfg := &config.Config{}
	cfg.Defaults()
	cfg.EnableOpenAI = true
	cfg.EnableAnthropic = true
	cfg.Router.PublicModelAliases = map[string]string{"coding": "local-coding"}

	reg := registry.NewRegistry([]manifest.Endpoint{
		{
			ID:        "rtx5090-qwen38-262k-01",
			Enabled:   true,
			Host:      manifest.Host{Name: "rtx5090", Address: "192.168.86.37", Priority: 10},
			Runtime:   manifest.Runtime{Type: "vllm", APIFamily: "openai", Port: 8201},
			Model:     manifest.Model{ServedModelName: "qwen3.8"},
			Context:   manifest.Context{MaxContextTokens: 262144},
			Routing:   manifest.RoutingPolicy{StaticCapacity: 1, Priority: 10},
		},
	}, nil)
	tel := telemetry.New()
	p := proxy.New(cfg, reg, tel, nil)
	a := api.New(cfg, reg, tel, p, nil)
	a.SetRescan(func() {})

	w := httptest.NewRecorder()
	a.Mux().ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/v1/models", nil))
	body := w.Body.String()
	if !strings.Contains(body, "local-coding") {
		t.Fatalf("models response missing alias: %s", body)
	}
	if !strings.Contains(body, "qwen3.8") {
		t.Fatalf("models response missing backend model: %s", body)
	}
	var parsed map[string]any
	if err := json.Unmarshal([]byte(body), &parsed); err != nil {
		t.Fatalf("models not JSON: %v", err)
	}
}

// TestCountTokens: /v1/messages/count_tokens returns a positive input_tokens.
func TestCountTokens(t *testing.T) {
	cfg := &config.Config{}
	cfg.Defaults()
	cfg.EnableAnthropic = true
	reg := registry.NewRegistry(nil, nil)
	tel := telemetry.New()
	p := proxy.New(cfg, reg, tel, nil)
	a := api.New(cfg, reg, tel, p, nil)

	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/messages/count_tokens",
		strings.NewReader(`{"model":"local-coding","messages":[{"role":"user","content":"a fairly long message to count"}]}`))
	a.Mux().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("count_tokens status %d: %s", w.Code, w.Body.String())
	}
	var out struct {
		InputTokens int `json:"input_tokens"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
		t.Fatalf("count_tokens not JSON: %v", err)
	}
	if out.InputTokens <= 0 {
		t.Fatalf("expected positive input_tokens, got %d", out.InputTokens)
	}
}
