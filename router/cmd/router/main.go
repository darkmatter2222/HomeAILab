// Command router is the ultra-fast local LLM router. It wires the control
// plane (discovery, health, lease watchdog) to the hot data plane (streaming
// proxy) and serves the client-facing + admin + metrics HTTP surface.
package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"llm-router/internal/api"
	"llm-router/internal/config"
	"llm-router/internal/discovery"
	"llm-router/internal/health"
	"llm-router/internal/proxy"
	"llm-router/internal/registry"
	"llm-router/internal/telemetry"
)

func main() {
	// Subcommand: health-probe (for the scratch-image healthcheck, which has
	// no shell). Exits 0 if /health is reachable, 1 otherwise.
	if len(os.Args) > 1 && os.Args[1] == "health-probe" {
		os.Exit(runHealthProbe())
	}

	cfgPath := os.Getenv("ROUTER_CONFIG")
	if cfgPath == "" {
		cfgPath = "config/router.yaml"
	}
	cfg, err := config.Load(cfgPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "config: %v\n", err)
		os.Exit(1)
	}
	log := func(format string, a ...any) { fmt.Printf(format+"\n", a...) }
	log("router: loaded config from %s", cfgPath)

	// Registry (static seed endpoints).
	reg := registry.NewRegistry(cfg.Endpoints, nil)
	tel := telemetry.New()
	prox := proxy.New(cfg, reg, tel, log)
	apih := api.New(cfg, reg, tel, prox, log)

	// Discovery + health control-plane workers.
	disc := discovery.NewWorker(cfg, reg, log)
	// Wire the rescan callback into the admin API.
	apih.SetRescan(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		disc.Rescan(ctx)
	})

	healthW := health.NewWorker(cfg, reg, log)

	// Endpoint stats -> telemetry (for /metrics gauges), refreshed on a
	// control-plane cadence (not the hot path).
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		ticker := time.NewTicker(2 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				view := reg.View()
				stats := make([]telemetry.EndpointStats, 0, len(view.All()))
				for _, e := range view.All() {
					stats = append(stats, telemetry.EndpointStats{
						ID:        e.Manifest.ID,
						Capacity:  e.Pool.Capacity(),
						Inflight:  int(e.Pool.Inflight()),
						Available: int(e.Pool.Available()),
						Healthy:   e.State.Healthy,
						Draining:  e.State.Draining,
						Priority:  e.Manifest.Routing.Priority,
					})
				}
				tel.SetEndpointStats(stats)
			}
		}
	}()

	// Start control-plane workers.
	if cfg.Discovery.Enabled {
		go disc.Run(ctx)
	}
	if cfg.Health.Enabled {
		go healthW.Run(ctx)
	}
	if cfg.Leases.Enabled {
		go disc.RunLeaseWatchdog(ctx)
	}

	// HTTP listener.
	srv := &http.Server{
		Addr:    cfg.Router.Bind + ":" + itoa(cfg.Router.Port),
		Handler: apih.Mux(),
		// Generous idle timeout; per-request upstream timeouts are on the proxy.
		ReadHeaderTimeout: 5 * time.Second,
	}
	go func() {
		log("router: listening on %s", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log("router: http server: %v", err)
			cancel()
		}
	}()

	// Graceful shutdown on SIGTERM/SIGINT: stop accepting, drain in-flight.
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGTERM, syscall.SIGINT)
	<-sig
	log("router: shutdown signal; draining in-flight")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutdownCancel()
	_ = srv.Shutdown(shutdownCtx)
	cancel()
	log("router: stopped")
}

// runHealthProbe does a local /health GET; 0 on 200, 1 otherwise.
func runHealthProbe() int {
	addr := os.Getenv("ROUTER_LISTEN_ADDR")
	if addr == "" {
		addr = "127.0.0.1:8001"
	}
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get("http://" + addr + "/health")
	if err != nil {
		return 1
	}
	resp.Body.Close()
	if resp.StatusCode == http.StatusOK {
		return 0
	}
	return 1
}

func itoa(n int) string {
	if n <= 0 {
		return "0"
	}
	var b []byte
	for n > 0 {
		b = append([]byte{byte('0' + n%10)}, b...)
		n /= 10
	}
	return string(b)
}
