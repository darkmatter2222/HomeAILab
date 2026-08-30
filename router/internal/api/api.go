// Package api wires the HTTP routes: the client-facing inference endpoints,
// the admin/status surface, /health, /metrics, and /v1/models.
package api

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	"llm-router/internal/config"
	"llm-router/internal/proxy"
	"llm-router/internal/registry"
	"llm-router/internal/routing"
	"llm-router/internal/telemetry"
)

// API bundles the router's HTTP handlers.
type API struct {
	cfg       *config.Config
	reg       *registry.Registry
	telemetry *telemetry.Telemetry
	proxy     *proxy.Proxy
	log       func(string, ...any)
	rescan    RescanFn
}

// New builds the API.
func New(cfg *config.Config, reg *registry.Registry, t *telemetry.Telemetry, p *proxy.Proxy, log func(string, ...any)) *API {
	return &API{cfg: cfg, reg: reg, telemetry: t, proxy: p, log: log}
}

// Mux returns the root http.Handler with all routes registered.
func (a *API) Mux() *http.ServeMux {
	mux := http.NewServeMux()

	// Client-facing inference (proxied to the selected endpoint).
	if a.cfg.EnableOpenAI {
		mux.HandleFunc("POST /v1/chat/completions", a.proxy.ServeHTTP)
		mux.HandleFunc("POST /v1/responses", a.proxy.ServeHTTP)
	}
	if a.cfg.EnableAnthropic {
		mux.HandleFunc("POST /v1/messages", a.proxy.ServeHTTP)
		mux.HandleFunc("POST /v1/messages/count_tokens", a.handleCountTokens)
	}

	// Status + metadata.
	mux.HandleFunc("GET /health", a.handleHealth)
	mux.HandleFunc("GET /v1/models", a.handleModels)
	mux.HandleFunc("GET /router/status", a.handleRouterStatus)

	// Metrics (control-plane scrape only; never in the request hot path).
	if a.cfg.Metrics.Enabled {
		mux.HandleFunc("GET "+a.cfg.Metrics.Path, a.telemetry.HandleMetrics)
	}

	// Admin.
	if a.cfg.Admin.Enabled {
		prefix := a.cfg.Admin.Prefix
		if prefix == "" {
			prefix = "/admin"
		}
		mux.HandleFunc("GET "+prefix+"/hosts", a.handleAdminHosts)
		mux.HandleFunc("GET "+prefix+"/endpoints", a.handleAdminEndpoints)
		mux.HandleFunc("GET "+prefix+"/routing-table", a.handleAdminRoutingTable)
		mux.HandleFunc("GET "+prefix+"/requests", a.handleAdminRequests)
		mux.HandleFunc("GET "+prefix+"/config", a.handleAdminConfig)
		mux.HandleFunc("POST "+prefix+"/discovery/rescan", a.handleRescan)
		// Per-endpoint lifecycle actions (drain/undrain/enable/disable).
		mux.HandleFunc("POST "+prefix+"/endpoints/", a.handleEndpointAction)
	}

	// 404 for anything else.
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "not_found", "path": r.URL.Path})
	})
	return mux
}

// handleHealth reports router health + how many endpoints are healthy.
func (a *API) handleHealth(w http.ResponseWriter, _ *http.Request) {
	view := a.reg.View()
	healthy := view.HealthyCount()
	writeJSON(w, http.StatusOK, map[string]any{
		"status":  "ok",
		"healthy": healthy,
		"total":   len(view.All()),
	})
}

// handleModels advertises the public alias + the backend served names.
func (a *API) handleModels(w http.ResponseWriter, _ *http.Request) {
	view := a.reg.View()
	data := make([]map[string]any, 0)
	// Public alias (if configured).
	if alias := a.cfg.Router.PublicModelAliases["coding"]; alias != "" {
		data = append(data, map[string]any{
			"id": alias, "object": "model", "owned_by": "llm-router", "root": "alias",
		})
	}
	// Backend served model names.
	seen := map[string]bool{}
	for _, e := range view.All() {
		name := e.Manifest.Model.ServedModelName
		if name == "" || seen[name] {
			continue
		}
		seen[name] = true
		data = append(data, map[string]any{
			"id": name, "object": "model", "owned_by": "vllm",
			"max_model_len": e.Manifest.Context.MaxContextTokens,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"object": "list", "data": data})
}

// handleRouterStatus returns a compact endpoint table for the live-traffic UI.
func (a *API) handleRouterStatus(w http.ResponseWriter, _ *http.Request) {
	view := a.reg.View()
	rows := make([]map[string]any, 0, len(view.All()))
	for _, e := range view.All() {
		rows = append(rows, map[string]any{
			"id":            e.Manifest.ID,
			"host":          e.Manifest.Host.Name,
			"port":          e.Manifest.Runtime.Port,
			"context":       e.Manifest.Context.MaxContextTokens,
			"capacity":      e.Pool.Capacity(),
			"inflight":      e.Pool.Inflight(),
			"available":     e.Pool.Available(),
			"healthy":       e.State.Healthy,
			"enabled":       e.State.Enabled,
			"draining":      e.State.Draining,
			"priority":      e.Manifest.Routing.Priority,
			"signature":     e.Manifest.Routing.SignatureGroup,
			"served_model":  e.Manifest.Model.ServedModelName,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"endpoints": rows})
}

// handleCountTokens estimates input tokens for the Anthropic count_tokens
// endpoint (no upstream call — the router's own estimator).
func (a *API) handleCountTokens(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	r.Body.Close()
	req := routing.Classify(body, "anthropic")
	writeJSON(w, http.StatusOK, map[string]any{"input_tokens": req.InputTokenEstimate})
}

// ---- admin ----

func (a *API) handleAdminHosts(w http.ResponseWriter, _ *http.Request) {
	rows := make([]map[string]any, 0)
	for _, h := range a.cfg.Hosts {
		rows = append(rows, map[string]any{"id": h.ID, "address": h.Address, "priority": h.Priority})
	}
	writeJSON(w, http.StatusOK, map[string]any{"hosts": rows})
}

func (a *API) handleAdminEndpoints(w http.ResponseWriter, _ *http.Request) {
	view := a.reg.View()
	rows := make([]map[string]any, 0, len(view.All()))
	for _, e := range view.All() {
		rows = append(rows, map[string]any{
			"id": e.Manifest.ID, "host": e.Manifest.Host.Name,
			"runtime": e.Manifest.Runtime.Type, "port": e.Manifest.Runtime.Port,
			"model": e.Manifest.Model.ServedModelName,
			"context": e.Manifest.Context.MaxContextTokens,
			"capacity": e.Pool.Capacity(), "inflight": e.Pool.Inflight(),
			"healthy": e.State.Healthy, "enabled": e.State.Enabled, "draining": e.State.Draining,
			"priority": e.Manifest.Routing.Priority, "signature": e.Manifest.Routing.SignatureGroup,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"endpoints": rows})
}

func (a *API) handleAdminRoutingTable(w http.ResponseWriter, _ *http.Request) {
	view := a.reg.View()
	ordered := make([]string, 0, len(view.All()))
	entries := view.All()
	// Deterministic order (priority, context, id) — the same order the data
	// plane would walk.
	ordered = view.IDs()
	writeJSON(w, http.StatusOK, map[string]any{"order": ordered, "count": len(entries)})
}

func (a *API) handleAdminRequests(w http.ResponseWriter, _ *http.Request) {
	// In-flight view (bounded; for diagnostics).
	view := a.reg.View()
	inflight := map[string]int64{}
	for _, e := range view.All() {
		inflight[e.Manifest.ID] = e.Pool.Inflight()
	}
	writeJSON(w, http.StatusOK, map[string]any{"inflight": inflight})
}

func (a *API) handleAdminConfig(w http.ResponseWriter, _ *http.Request) {
	// Redacted config snapshot (hosts + endpoint ids).
	ids := a.reg.View().IDs()
	writeJSON(w, http.StatusOK, map[string]any{
		"listen": a.cfg.Router.Bind + ":" + itoa(int(a.cfg.Router.Port)),
		"port_contracts": a.cfg.PortContracts,
		"endpoint_ids":   ids,
	})
}

// handleRescan triggers a discovery rescan.
func (a *API) handleRescan(w http.ResponseWriter, _ *http.Request) {
	a.writeRescan(w)
}

// handleEndpointAction handles POST /admin/endpoints/{id}/{action}.
func (a *API) handleEndpointAction(w http.ResponseWriter, r *http.Request) {
	// path = /admin/endpoints/{id}/{action}
	rest := strings.TrimPrefix(r.URL.Path, "/admin/endpoints/")
	parts := strings.Split(rest, "/")
	if len(parts) != 2 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "expected /admin/endpoints/{id}/{action}"})
		return
	}
	id, action := parts[0], parts[1]
	view := a.reg.View()
	e := view.Get(id)
	if e == nil {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "endpoint_not_found", "id": id})
		return
	}
	switch action {
	case "drain":
		e.State.Draining = true
	case "undrain":
		e.State.Draining = false
	case "enable":
		e.State.Enabled = true
	case "disable":
		e.State.Enabled = false
	default:
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "unknown_action", "action": action})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"id": id, "action": action, "ok": true})
}

func (a *API) writeRescan(w http.ResponseWriter) {
	// The discovery worker owns Rescan; the API triggers it via a callback set
	// in main. For v1, we store it on the API.
	if a.rescan != nil {
		a.rescan()
		writeJSON(w, http.StatusOK, map[string]any{"rescan": true})
	} else {
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"error": "rescan_not_wired"})
	}
}

// RescanFn is set by main so /admin/discovery/rescan can reach the worker.
type RescanFn func()

// SetRescan wires the rescan callback.
func (a *API) SetRescan(fn RescanFn) { a.rescan = fn }

// writeJSON writes a JSON object with the given status.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// itoa renders an int as a string (for the listen address).
func itoa(n int) string { return strconv.Itoa(n) }
