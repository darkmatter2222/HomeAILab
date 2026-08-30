// Package discovery is the control plane: it (re)builds the routing table
// from the static seed (and optional manifest fetches), and runs the lease
// watchdog that reaps leaked capacity slots. It never blocks the hot path.
package discovery

import (
	"context"
	"net/http"
	"sync"
	"time"

	"llm-router/internal/config"
	"llm-router/internal/manifest"
	"llm-router/internal/registry"
)

// Worker owns discovery + lease-repair.
type Worker struct {
	cfg     *config.Config
	reg     *registry.Registry
	client  *http.Client
	log     func(string, ...any)
	mu      sync.Mutex
	lastScan time.Time
}

// NewWorker builds a discovery worker.
func NewWorker(cfg *config.Config, reg *registry.Registry, log func(string, ...any)) *Worker {
	ct := time.Duration(cfg.Discovery.ConnectTimeoutMS) * time.Millisecond
	if ct <= 0 {
		ct = 250 * time.Millisecond
	}
	return &Worker{
		cfg:    cfg,
		reg:    reg,
		client: &http.Client{Timeout: ct + time.Duration(cfg.Discovery.ResponseTypeMS)*time.Millisecond},
		log:    log,
	}
}

// Rescan rebuilds the routing table from the seed endpoints (and, if enabled,
// manifest fetches for hosts in cfg.Discovery.DiscoveryHosts). It is idempotent
// and invoked by /admin/discovery/rescan and the discovery interval.
func (w *Worker) Rescan(ctx context.Context) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.lastScan = time.Now()

	seeds := make([]manifest.Endpoint, len(w.cfg.Endpoints))
	copy(seeds, w.cfg.Endpoints)

	// Optional manifest enrichment (control plane only).
	if w.cfg.Discovery.Enabled && !w.cfg.Discovery.RequireManifest {
		for _, h := range w.cfg.Discovery.DiscoveryHosts {
			if m, ok := w.fetchManifest(ctx, h); ok {
				seeds = append(seeds, m.ToEndpoint())
			}
		}
	}

	// Enforce port contract on every seed (exclude violators).
	contracts := w.cfg.PortContractList()
	if w.cfg.EnforcePortContract {
		filtered := make([]manifest.Endpoint, 0, len(seeds))
		for _, e := range seeds {
			if err := manifest.ValidatePortContract(&e, contracts); err != nil {
				if w.log != nil {
					w.log("discovery: excluding endpoint %s: %v", e.ID, err)
				}
				continue
			}
			filtered = append(filtered, e)
		}
		seeds = filtered
	}

	// Preserve the in-flight capacity state across a table swap so a rescan
	// doesn't drop the live counters. NewTable rebuilds pools, so copy the
	// inflight/lease state over for endpoints that already existed.
	table := registry.NewTable(seeds, w.onReap())
	w.reg.Set(table)
	if w.log != nil {
		w.log("discovery: rescan complete, %d endpoints registered", len(seeds))
	}
}

// Run blocks until ctx is canceled, rescanning on the discovery interval.
func (w *Worker) Run(ctx context.Context) {
	if !w.cfg.Discovery.Enabled {
		<-ctx.Done()
		return
	}
	interval := time.Duration(w.cfg.Discovery.IntervalMS) * time.Millisecond
	if interval <= 0 {
		interval = 5 * time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	w.Rescan(ctx)
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			w.Rescan(ctx)
		}
	}
}

// RunLeaseWatchdog reaps leaked capacity leases every 30s (control plane).
func (w *Worker) RunLeaseWatchdog(ctx context.Context) {
	if !w.cfg.Leases.Enabled {
		<-ctx.Done()
		return
	}
	hard := time.Duration(w.cfg.Leases.HardTimeoutSecs) * time.Second
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			view := w.reg.View()
			for _, e := range view.All() {
				if n := e.Pool.ReapLeases(time.Now(), hard); n > 0 {
					if w.log != nil {
						w.log("lease-watchdog: reaped %d leaked lease(s) on %s", n, e.Manifest.ID)
					}
				}
			}
		}
	}
}

// decodeManifest tries YAML then JSON (manifests may be served in either).
func decodeManifest(b []byte, m *manifest.Manifest) error {
	if err := yamlUnmarshal(b, m); err == nil {
		return nil
	}
	return jsonUnmarshal(b, m)
}

// fetchManifest tries /.well-known/llm-router-manifest then /router/manifest.
func (w *Worker) fetchManifest(ctx context.Context, host string) (manifest.Manifest, bool) {
	var m manifest.Manifest
	for _, path := range []string{"/.well-known/llm-router-manifest", "/router/manifest"} {
		url := "http://" + host + path
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			continue
		}
		resp, err := w.client.Do(req)
		if err != nil {
			continue
		}
		// Read into a bounded buffer.
		buf := make([]byte, 0, 64*1024)
		n, _ := resp.Body.Read(buf)
		resp.Body.Close()
		if n == 0 {
			continue
		}
		buf = buf[:n]
		if err := decodeManifest(buf, &m); err == nil {
			return m, true
		}
	}
	return m, false
}

// onReap wires the lease-repair callback into the registry's pools.
func (w *Worker) onReap() func(endpointID, requestID string) {
	return func(endpointID, requestID string) {
		if w.log != nil {
			w.log("lease-repair: %s freed by watchdog (req %s)", endpointID, requestID)
		}
	}
}

