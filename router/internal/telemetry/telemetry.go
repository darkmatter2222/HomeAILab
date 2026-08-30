// Package telemetry exposes Prometheus metrics and structured routing
// decision logs. It is hand-rolled (no client_golang) to keep the image
// small; labels are bounded (endpoint_id, reason, status) to avoid
// cardinality explosion.
package telemetry

import (
	"net/http"
	"strings"
	"sync"
)

// Telemetry is the metrics + logging core.
type Telemetry struct {
	mu sync.Mutex
	// counters (atomic-like via mutex for simplicity; bounded label sets)
	requestsTotal  map[string]int // status -> count
	rejections     map[string]int // reason -> count
	upstreamErrs   map[string]int // endpoint_id -> count
	clientDiscon   int
	routeSelection map[string]int // result -> count
	lastStats      []EndpointStats
}

// New builds a telemetry collector.
func New() *Telemetry {
	return &Telemetry{
		requestsTotal:  map[string]int{},
		rejections:     map[string]int{},
		upstreamErrs:   map[string]int{},
		routeSelection: map[string]int{},
	}
}

// RecordRequest bumps the requests counter by status.
func (t *Telemetry) RecordRequest(endpointID string, status int) {
	if status < 0 {
		return
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	t.requestsTotal[itoa(status)+"xx"]++
}

// RecordRejection bumps a rejection reason counter.
func (t *Telemetry) RecordRejection(reason string) {
	t.mu.Lock()
	t.rejections[reason]++
	t.mu.Unlock()
}

// RecordUpstreamError bumps the upstream-error counter for an endpoint.
func (t *Telemetry) RecordUpstreamError(endpointID string) {
	t.mu.Lock()
	t.upstreamErrs[endpointID]++
	t.mu.Unlock()
}

// RecordClientDisconnect bumps the client-disconnect counter.
func (t *Telemetry) RecordClientDisconnect() {
	t.mu.Lock()
	t.clientDiscon++
	t.mu.Unlock()
}

// RecordSelection records a route-selection outcome (bounded by result codes).
func (t *Telemetry) RecordSelection(candidates []string) {
	t.mu.Lock()
	defer t.mu.Unlock()
	for _, c := range candidates {
		if c == "selected" {
			t.routeSelection["selected"]++
		} else {
			// keep a bounded set: only count the top few distinct reasons
			t.routeSelection[c]++
		}
	}
}

// RecordRouteSelectionTotal bumps the generic route-selection counter.
func (t *Telemetry) RecordRouteSelectionTotal() {
	t.mu.Lock()
	t.routeSelection["total"]++
	t.mu.Unlock()
}

// EndpointStats is a snapshot of per-endpoint gauges for /metrics and the UI.
type EndpointStats struct {
	ID        string
	Capacity  int
	Inflight  int
	Available int
	Healthy   bool
	Draining  bool
	Priority  int
}

// SetEndpointStats is called by the registry to expose live gauges.
func (t *Telemetry) SetEndpointStats(stats []EndpointStats) {
	t.mu.Lock()
	t.lastStats = stats
	t.mu.Unlock()
}

// HandleMetrics serves the Prometheus text-format endpoint.
func (t *Telemetry) HandleMetrics(w http.ResponseWriter, _ *http.Request) {
	t.mu.Lock()
	defer t.mu.Unlock()
	var b strings.Builder
	b.WriteString("# HELP router_requests_total Total proxied requests by status class\n")
	b.WriteString("# TYPE router_requests_total counter\n")
	for k, v := range t.requestsTotal {
		b.WriteString("router_requests_total{status_class=\"" + k + "\"} " + itoa(v) + "\n")
	}
	b.WriteString("# HELP router_rejections_total Total routing rejections by reason\n")
	b.WriteString("# TYPE router_rejections_total counter\n")
	for k, v := range t.rejections {
		b.WriteString("router_rejections_total{reason=\"" + k + "\"} " + itoa(v) + "\n")
	}
	b.WriteString("# HELP router_upstream_errors_total Upstream errors by endpoint\n")
	b.WriteString("# TYPE router_upstream_errors_total counter\n")
	for k, v := range t.upstreamErrs {
		b.WriteString("router_upstream_errors_total{endpoint_id=\"" + k + "\"} " + itoa(v) + "\n")
	}
	b.WriteString("# HELP router_client_disconnects_total Client disconnects\n")
	b.WriteString("# TYPE router_client_disconnects_total counter\n")
	b.WriteString("router_client_disconnects_total " + itoa(t.clientDiscon) + "\n")
	b.WriteString("# HELP router_route_selection_total Route-selection outcomes\n")
	b.WriteString("# TYPE router_route_selection_total counter\n")
	for k, v := range t.routeSelection {
		b.WriteString("router_route_selection_total{result=\"" + k + "\"} " + itoa(v) + "\n")
	}
	// Per-endpoint gauges.
	for _, s := range t.lastStats {
		b.WriteString("router_endpoint_capacity{endpoint_id=\"" + s.ID + "\"} " + itoa(s.Capacity) + "\n")
		b.WriteString("router_endpoint_inflight{endpoint_id=\"" + s.ID + "\"} " + itoa(s.Inflight) + "\n")
		b.WriteString("router_endpoint_available{endpoint_id=\"" + s.ID + "\"} " + itoa(s.Available) + "\n")
		healthy := 0
		if s.Healthy {
			healthy = 1
		}
		b.WriteString("router_endpoint_healthy{endpoint_id=\"" + s.ID + "\"} " + itoa(healthy) + "\n")
		b.WriteString("router_endpoint_registered{endpoint_id=\"" + s.ID + "\"} 1\n")
	}
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	_, _ = w.Write([]byte(b.String()))
}

// lastStats is the most recent endpoint snapshot (set by the control plane).
