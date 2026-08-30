// Package health runs the asynchronous endpoint health worker. It is the
// ONLY place the router touches an upstream /health. The data plane reads the
// resulting State.Healthy flag and never probes itself.
package health

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"llm-router/internal/config"
	"llm-router/internal/registry"
)

// Worker polls each endpoint's health path on an interval and drives the
// threshold-based state machine.
type Worker struct {
	cfg    *config.Config
	reg    *registry.Registry
	client *http.Client
	log    func(string, ...any)
}

// NewWorker builds a health worker.
func NewWorker(cfg *config.Config, reg *registry.Registry, log func(string, ...any)) *Worker {
	timeout := time.Duration(cfg.Health.TimeoutMS) * time.Millisecond
	return &Worker{
		cfg:    cfg,
		reg:    reg,
		client: &http.Client{Timeout: timeout},
		log:    log,
	}
}

// Run blocks until ctx is canceled, polling every cfg.Health.IntervalMS.
func (w *Worker) Run(ctx context.Context) {
	interval := time.Duration(w.cfg.Health.IntervalMS) * time.Millisecond
	if interval <= 0 {
		interval = 2 * time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	// Poll once immediately so /health isn't stale at boot.
	w.pollAll(ctx)
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			w.pollAll(ctx)
		}
	}
}

// pollAll checks every endpoint once.
func (w *Worker) pollAll(ctx context.Context) {
	view := w.reg.View()
	for _, e := range view.All() {
		path := e.Manifest.Health.Path
		if path == "" {
			path = "/health"
		}
		url := fmt.Sprintf("http://%s:%d%s", e.Manifest.Host.Address, e.Manifest.Runtime.Port, path)
		ok := w.probe(ctx, url)
		w.apply(e, ok)
	}
}

// probe does a single GET; ok is true on an acceptable status.
func (w *Worker) probe(ctx context.Context, url string) bool {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false
	}
	resp, err := w.client.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	if len(w.cfg.Health.AcceptableStatus) == 0 {
		return resp.StatusCode == http.StatusOK
	}
	for _, s := range w.cfg.Health.AcceptableStatus {
		if resp.StatusCode == s {
			return true
		}
	}
	return false
}

// apply drives the threshold state machine for one endpoint.
func (w *Worker) apply(e *registry.Entry, ok bool) {
	st := e.State
	st.HealthyNow = ok
	if ok {
		st.HealthFailures = 0
		st.HealthSuccesses++
		if st.Healthy {
			return
		}
		if st.HealthSuccesses >= w.cfg.Health.RecoveryThreshold {
			st.Healthy = true
			st.HealthSuccesses = 0
			if w.log != nil {
				w.log("health: %s recovered (HEALTHY)", e.Manifest.ID)
			}
		}
	} else {
		st.HealthSuccesses = 0
		st.HealthFailures++
		if !st.Healthy {
			return
		}
		if st.HealthFailures >= w.cfg.Health.FailureThreshold {
			st.Healthy = false
			st.HealthFailures = 0
			if w.log != nil {
				w.log("health: %s UNHEALTHY", e.Manifest.ID)
			}
		}
	}
}
