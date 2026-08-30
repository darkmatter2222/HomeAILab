package tests

import (
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"testing"

	"llm-router/internal/config"
	"llm-router/internal/manifest"
	"llm-router/internal/proxy"
	"llm-router/internal/registry"
	"llm-router/internal/telemetry"
)

// makeRegistry builds a registry with one endpoint pointing at a fake upstream
// (the httptest server) so we can observe failover behavior.
func makeRegistry(t *testing.T, upstream *httptest.Server) *registry.Registry {
	u, _ := url.Parse(upstream.URL) // URL is a string
	host, port, _ := net.SplitHostPort(u.Host)
	if host == "" {
		host = "127.0.0.1"
	}
	p, _ := strconv.Atoi(port)
	eps := []manifest.Endpoint{
		{
			ID:           "ep-1",
			Enabled:      true,
			Host:         manifest.Host{Name: "t", Address: host, Priority: 10},
			Runtime:      manifest.Runtime{Type: "vllm", APIFamily: "openai", Port: p},
			Model:        manifest.Model{ServedModelName: "qwen3.8"},
			Capabilities: manifest.Capabilities{Text: true, Tools: true, Streaming: true},
			Context:      manifest.Context{MaxContextTokens: 262144},
			Routing:      manifest.RoutingPolicy{StaticCapacity: 1, Priority: 10},
		},
	}
	return registry.NewRegistry(eps, nil)
}

// TestPreStreamFailoverNoLeak: upstream that 500s before any body byte ->
// the slot is released (no leak) and the client sees 502.
func TestPreStreamFailoverNoLeak(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer up.Close()

	reg := makeRegistry(t, up)
	cfg := &config.Config{}
	cfg.Defaults()
	cfg.EnableOpenAI = true
	p := proxy.New(cfg, reg, telemetry.New(), nil)

	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions",
		strings.NewReader(`{"model":"local-coding","messages":[{"role":"user","content":"hi"}],"max_tokens":4}`))
	req.Header.Set("Content-Type", "application/json")
	p.ServeHTTP(w, req)

	// The upstream's 500 status propagates (or a connect error yields 502).
	// Either way it's a 5xx, and crucially the slot must be released.
	if w.Code < 500 || w.Code > 599 {
		t.Fatalf("expected 5xx on upstream error, got %d (body %s)", w.Code, w.Body.String())
	}
	// Slot must be released (no leak).
	if got := reg.View().Get("ep-1").Pool.Inflight(); got != 0 {
		t.Fatalf("inflight not released after upstream error: %d", got)
	}
}

// TestStreamReleaseAfterNormalCompletion: a normal (non-stream) 200 response
// -> 200 to client, slot released.
func TestStreamReleaseAfterNormalCompletion(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	defer up.Close()

	reg := makeRegistry(t, up)
	cfg := &config.Config{}
	cfg.Defaults()
	cfg.EnableOpenAI = true
	p := proxy.New(cfg, reg, telemetry.New(), nil)

	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions",
		strings.NewReader(`{"model":"local-coding","messages":[{"role":"user","content":"hi"}],"max_tokens":4}`))
	p.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d (body %s)", w.Code, w.Body.String())
	}
	if got := reg.View().Get("ep-1").Pool.Inflight(); got != 0 {
		t.Fatalf("inflight not released after completion: %d", got)
	}
}
