// Package config loads router.yaml, applies ROUTER_* environment overrides
// (env wins), and asserts the hot-path invariants at boot.
package config

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"

	"llm-router/internal/manifest"
)

// Config is the fully-resolved router configuration.
type Config struct {
	Version string `yaml:"version"`

	Router struct {
		Bind string `yaml:"bind"`
		Port int    `yaml:"port"`

		PublicModelAliases map[string]string `yaml:"public_model_aliases"`

		HotPath struct {
			PerformHealthChecks bool `yaml:"perform_health_checks"`
			QueryMetrics       bool `yaml:"query_metrics"`
			QueryGPUState      bool `yaml:"query_gpu_state"`
			QueryModelsEndpoint bool `yaml:"query_models_endpoint"`
		} `yaml:"hot_path"`

		Request struct {
			DefaultMaxOutputTokens  int `yaml:"default_max_output_tokens"`
			ContextReserveTokens    int `yaml:"context_reserve_tokens"`
			ContextReservePercent   int `yaml:"context_reserve_percent"`
		} `yaml:"request"`

		Retry struct {
			ReservationRetries     int  `yaml:"reservation_retries"`
			UpstreamConnectRetries int  `yaml:"upstream_connect_retries"`
			AfterStreamStart       bool `yaml:"retry_after_stream_started"`
		} `yaml:"retry"`
	} `yaml:"router"`

	Hosts []struct {
		ID       string `yaml:"id"`
		Address  string `yaml:"address"`
		Priority int    `yaml:"priority"`
	} `yaml:"hosts"`

	PortContracts map[string]struct {
		Start int `yaml:"start"`
		End   int `yaml:"end"`
	} `yaml:"port_contracts"`

	Discovery struct {
		Enabled              bool     `yaml:"enabled"`
		IntervalMS           int      `yaml:"interval_ms"`
		ConnectTimeoutMS     int      `yaml:"connect_timeout_ms"`
		ResponseTypeMS       int      `yaml:"response_timeout_ms"`
		RequireManifest      bool     `yaml:"require_manifest"`
		RejectUnknownRuntime bool     `yaml:"reject_unknown_runtime"`
		RejectPortContract   bool     `yaml:"reject_port_contract_violation"`
		DiscoveryHosts       []string `yaml:"discovery_hosts"`
	} `yaml:"discovery"`

	Health struct {
		Enabled           bool  `yaml:"enabled"`
		IntervalMS        int   `yaml:"interval_ms"`
		TimeoutMS         int   `yaml:"timeout_ms"`
		FailureThreshold  int   `yaml:"failure_threshold"`
		RecoveryThreshold int   `yaml:"recovery_threshold"`
		AcceptableStatus  []int `yaml:"acceptable_status"`
	} `yaml:"health"`

	Context struct {
		Classes                  []int `yaml:"classes"`
		ReserveTokens            int   `yaml:"reserve_tokens"`
		ReservePercent           int   `yaml:"reserve_percent"`
		PreferSmallestSufficient bool  `yaml:"prefer_smallest_sufficient"`
	} `yaml:"context"`

	Routing struct {
		Strategy  string   `yaml:"strategy"`
		HostOrder []string `yaml:"host_order"`
	} `yaml:"routing"`

	CapacityRules []struct {
		Match struct {
			Host string `yaml:"host"`
			Port int    `yaml:"port"`
		} `yaml:"match"`
		Capacity int `yaml:"capacity"`
	} `yaml:"capacity_rules"`

	SignatureGroups map[string]struct {
		APIFamily    string `yaml:"api_family"`
		ModelFamily  string `yaml:"model_family"`
		ToolSchema   string `yaml:"tool_schema"`
		Tools        bool   `yaml:"tools"`
		Streaming    bool   `yaml:"streaming"`
		ThinkingMode bool   `yaml:"thinking_mode"`
	} `yaml:"signature_groups"`

	Endpoints []manifest.Endpoint `yaml:"endpoints"`

	Leases struct {
		Enabled         bool `yaml:"enabled"`
		HardTimeoutSecs int  `yaml:"hard_timeout_seconds"`
	} `yaml:"leases"`

	Affinity struct {
		Enabled       bool   `yaml:"enabled"`
		Mode          string `yaml:"mode"`
		AllowFallback bool   `yaml:"allow_fallback"`
	} `yaml:"affinity"`

	Logging struct {
		RoutingDecisions   bool `yaml:"routing_decisions"`
		RejectedCandidates bool `yaml:"rejected_candidates"`
	} `yaml:"logging"`

	Upstream struct {
		ConnectTimeoutMS        int `yaml:"connect_timeout_ms"`
		ResponseHeaderTimeoutMS int `yaml:"response_header_timeout_ms"`
	} `yaml:"upstream"`

	EnableOpenAI    bool `yaml:"enable_openai"`
	EnableAnthropic bool `yaml:"enable_anthropic"`

	Admin struct {
		Enabled bool   `yaml:"enabled"`
		Prefix  string `yaml:"prefix"`
	} `yaml:"admin"`

	Metrics struct {
		Enabled bool   `yaml:"enabled"`
		Path    string `yaml:"path"`
	} `yaml:"metrics"`

	HealthPath string `yaml:"health_path"`

	// --- flags driven by the hot-path env vars (not in the YAML schema) ---
	RoutingStrategyDeterministic bool `yaml:"-"`
	AtomicReservations           bool `yaml:"-"`
	ReleaseOnStreamEnd           bool `yaml:"-"`
	EnforcePortContract          bool `yaml:"-"`
	EnforceSignatures            bool `yaml:"-"`
	RetryBeforeStreamStart       bool `yaml:"-"`
}

// PortContractList converts the map form into the typed list the manifest
// validator expects.
func (c *Config) PortContractList() []manifest.PortContract {
	var out []manifest.PortContract
	for rt, r := range c.PortContracts {
		out = append(out, manifest.PortContract{Runtime: rt, Start: r.Start, End: r.End})
	}
	return out
}

// Defaults fills zero-valued fields with the handoff-recommended values.
func (c *Config) Defaults() {
	if c.Router.Bind == "" {
		c.Router.Bind = "0.0.0.0"
	}
	if c.Router.Port == 0 {
		c.Router.Port = 8001
	}
	if c.Router.Request.DefaultMaxOutputTokens == 0 {
		c.Router.Request.DefaultMaxOutputTokens = 16384
	}
	if c.Router.Request.ContextReserveTokens == 0 {
		c.Router.Request.ContextReserveTokens = 4096
	}
	if c.Router.Request.ContextReservePercent == 0 {
		c.Router.Request.ContextReservePercent = 5
	}
	if c.Router.Retry.ReservationRetries == 0 {
		c.Router.Retry.ReservationRetries = 3
	}
	if c.Health.IntervalMS == 0 {
		c.Health.IntervalMS = 2000
	}
	if c.Health.TimeoutMS == 0 {
		c.Health.TimeoutMS = 750
	}
	if c.Health.FailureThreshold == 0 {
		c.Health.FailureThreshold = 2
	}
	if c.Health.RecoveryThreshold == 0 {
		c.Health.RecoveryThreshold = 2
	}
	if c.Discovery.IntervalMS == 0 {
		c.Discovery.IntervalMS = 5000
	}
	if c.Leases.HardTimeoutSecs == 0 {
		c.Leases.HardTimeoutSecs = 7200
	}
	if c.Upstream.ConnectTimeoutMS == 0 {
		c.Upstream.ConnectTimeoutMS = 250
	}
	if c.Upstream.ResponseHeaderTimeoutMS == 0 {
		c.Upstream.ResponseHeaderTimeoutMS = 750
	}
	if c.Metrics.Path == "" {
		c.Metrics.Path = "/metrics"
	}
	if c.HealthPath == "" {
		c.HealthPath = "/health"
	}
	if c.Admin.Prefix == "" {
		c.Admin.Prefix = "/admin"
	}
	// When the env-driven hot-path flags were never set, default them to the
	// handoff-recommended (correct) values.
	if !c.RoutingStrategyDeterministic {
		c.RoutingStrategyDeterministic = true
	}
	c.AtomicReservations = true
	c.ReleaseOnStreamEnd = true
	c.EnforcePortContract = true
	c.EnforceSignatures = true
	c.RetryBeforeStreamStart = true
}

// Load reads the YAML file (path), applies env overrides, and returns the config.
func Load(path string) (*Config, error) {
	c := &Config{}
	if data, err := os.ReadFile(path); err == nil {
		if err := yaml.Unmarshal(data, c); err != nil {
			return nil, fmt.Errorf("config: parse %s: %w", path, err)
		}
	} else if !os.IsNotExist(err) {
		return nil, fmt.Errorf("config: read %s: %w", path, err)
	}
	c.applyEnv()
	c.Defaults()
	return c, nil
}

// applyEnv overlays ROUTER_* env vars on the YAML (env wins).
func (c *Config) applyEnv() {
	set := func(key string, fn func(string)) {
		if v, ok := os.LookupEnv(key); ok {
			fn(v)
		}
	}
	bint := func(key string, dst *bool) {
		set(key, func(v string) {
			if b, err := strconv.ParseBool(v); err == nil {
				*dst = b
			}
		})
	}
	intt := func(key string, dst *int) {
		set(key, func(v string) {
			if n, err := strconv.Atoi(v); err == nil {
				*dst = n
			}
		})
	}

	set("ROUTER_LISTEN_ADDR", func(v string) {
		parts := strings.SplitN(v, ":", 2)
		if len(parts) == 2 {
			c.Router.Bind = parts[0]
			if p, err := strconv.Atoi(parts[1]); err == nil {
				c.Router.Port = p
			}
		}
	})
	bint("ROUTER_ENABLE_OPENAI_API", &c.EnableOpenAI)
	bint("ROUTER_ENABLE_ANTHROPIC_API", &c.EnableAnthropic)
	bint("ROUTER_DYNAMIC_GPU_CAPACITY", &c.Router.HotPath.QueryGPUState)
	bint("ROUTER_REQUEST_PATH_HEALTH_CHECKS", &c.Router.HotPath.PerformHealthChecks)
	bint("ROUTER_DETERMINISTIC_ROUTING", &c.RoutingStrategyDeterministic)
	bint("ROUTER_ATOMIC_RESERVATIONS", &c.AtomicReservations)
	bint("ROUTER_RELEASE_ON_STREAM_END", &c.ReleaseOnStreamEnd)
	bint("ROUTER_PREFER_SMALLEST_SUFFICIENT_CONTEXT", &c.Context.PreferSmallestSufficient)
	bint("ROUTER_ENFORCE_PORT_CONTRACT", &c.EnforcePortContract)
	bint("ROUTER_ENFORCE_SIGNATURES", &c.EnforceSignatures)
	bint("ROUTER_METRICS_ENABLED", &c.Metrics.Enabled)
	bint("ROUTER_ADMIN_ENABLED", &c.Admin.Enabled)
	bint("ROUTER_DISCOVERY_ENABLED", &c.Discovery.Enabled)
	bint("ROUTER_HEALTH_ENABLED", &c.Health.Enabled)
	bint("ROUTER_LOG_ROUTING_DECISIONS", &c.Logging.RoutingDecisions)
	bint("ROUTER_RETRY_BEFORE_STREAM_START", &c.RetryBeforeStreamStart)
	bint("ROUTER_RETRY_AFTER_STREAM_START", &c.Router.Retry.AfterStreamStart)
	intt("ROUTER_CONTEXT_RESERVE_TOKENS", &c.Router.Request.ContextReserveTokens)
	intt("ROUTER_CONTEXT_RESERVE_PERCENT", &c.Router.Request.ContextReservePercent)
	intt("ROUTER_UPSTREAM_CONNECT_TIMEOUT_MS", &c.Upstream.ConnectTimeoutMS)
	intt("ROUTER_UPSTREAM_RESPONSE_HEADER_TIMEOUT_MS", &c.Upstream.ResponseHeaderTimeoutMS)
	intt("ROUTER_CAPACITY_LEASE_HARD_TIMEOUT_SEC", &c.Leases.HardTimeoutSecs)
	intt("ROUTER_DISCOVERY_INTERVAL_MS", &c.Discovery.IntervalMS)
	intt("ROUTER_HEALTH_INTERVAL_MS", &c.Health.IntervalMS)
	intt("ROUTER_HEALTH_TIMEOUT_MS", &c.Health.TimeoutMS)
	intt("ROUTER_HEALTH_FAILURE_THRESHOLD", &c.Health.FailureThreshold)
	intt("ROUTER_HEALTH_RECOVERY_THRESHOLD", &c.Health.RecoveryThreshold)
	set("ROUTER_PUBLIC_MODEL_ALIAS", func(v string) {
		if c.Router.PublicModelAliases == nil {
			c.Router.PublicModelAliases = map[string]string{}
		}
		c.Router.PublicModelAliases["coding"] = v
	})
	set("ROUTER_DISCOVERY_HOSTS", func(v string) {
		c.Discovery.DiscoveryHosts = splitCSV(v)
	})
	set("ROUTER_CONTEXT_CLASSES", func(v string) {
		c.Context.Classes = nil
		for _, f := range strings.Split(v, ",") {
			if n, err := strconv.Atoi(strings.TrimSpace(f)); err == nil {
				c.Context.Classes = append(c.Context.Classes, n)
			}
		}
	})
	set("ROUTER_ENDPOINTS_JSON", func(v string) {
		v = strings.TrimSpace(v)
		if v == "" {
			return
		}
		if eps, err := parseEndpointsJSON(v); err == nil {
			c.Endpoints = append(c.Endpoints, eps...)
		}
	})
}

func splitCSV(v string) []string {
	var out []string
	for _, p := range strings.Split(v, ",") {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

// parseEndpointsJSON decodes the ROUTER_ENDPOINTS_JSON env (a JSON array of
// endpoints) into manifest.Endpoints.
func parseEndpointsJSON(v string) ([]manifest.Endpoint, error) {
	var eps []manifest.Endpoint
	if err := json.Unmarshal([]byte(v), &eps); err != nil {
		return nil, err
	}
	return eps, nil
}
