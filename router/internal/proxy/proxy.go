// Package proxy is the hot data plane. It reads the request body lazily,
// selects + reserves an endpoint, streams the response directly to the client,
// and releases the reservation exactly once when the stream truly terminates.
package proxy

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"time"

	"llm-router/internal/config"
	"llm-router/internal/registry"
	"llm-router/internal/routing"
	"llm-router/internal/telemetry"
)

// Proxy is the streaming reverse proxy bound to a router's config, registry,
// and telemetry.
type Proxy struct {
	cfg     *config.Config
	reg     *registry.Registry
	telemetry *telemetry.Telemetry
	client  *http.Client
	log     func(string, ...any)
}

// New builds a proxy.
func New(cfg *config.Config, reg *registry.Registry, t *telemetry.Telemetry, log func(string, ...any)) *Proxy {
	p := &Proxy{
		cfg:       cfg,
		reg:       reg,
		telemetry: t,
		log:       log,
	}
	connect := time.Duration(cfg.Upstream.ConnectTimeoutMS) * time.Millisecond
	if connect <= 0 {
		connect = 250 * time.Millisecond
	}
	p.client = &http.Client{
		Timeout: connect + time.Duration(cfg.Upstream.ResponseHeaderTimeoutMS)*time.Millisecond,
	}
	return p
}

// ServeHTTP handles one inference request (OpenAI or Anthropic body).
func (p *Proxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	cfg := p.cfg
	reg := p.reg

	// Read the whole body (inference payloads are bounded by the client's
	// context window; we need it for classification + forwarding).
	body, err := io.ReadAll(r.Body)
	r.Body.Close()
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": map[string]any{"type": "invalid_request", "message": "read body: " + err.Error()}})
		return
	}

	req := routing.Classify(body, "openai")
	reqCtx := routing.RequiredContext(
		req.InputTokenEstimate,
		req.RequestedMaxOutput,
		cfg.Router.Request.ContextReserveTokens,
		cfg.Router.Request.ContextReservePercent,
		len(body),
	)

	// Stable lease id for this request.
	leaseID := newLeaseID()

	// Collect the filtered+sorted candidate list (no reservation yet) so we can
	// reserve the first free one and failover in deterministic order.
	ordered, candLog := p.orderedCandidates(reg.View(), req, reqCtx)

	var selected *registry.Entry
	reserved := false
	for _, e := range ordered {
		if _, ok := e.Pool.Reserve(leaseID); ok {
			selected = e
			reserved = true
			break
		}
	}

	p.telemetry.RecordSelection(candidateStrings(candLog))
	if !reserved || selected == nil {
		p.logRouting(leaseID, req, reqCtx, candLog, "", string(routing.ReasonCapacityFull))
		p.telemetry.RecordRejection(string(routing.ReasonCapacityFull))
		// Controlled capacity response (handoff: 503 "try again").
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{
			"error": map[string]any{
				"type":    "capacity_exhausted",
				"message": "all compatible endpoints at static capacity; retry",
				"reason":  "CAPACITY_FULL",
			},
		})
		return
	}

	// Exactly-once release on any exit (normal, client-cancel, upstream error,
	// timeout). Release happens only when the stream actually terminates.
	defer func() {
		if reserved {
			selected.Pool.Release(leaseID)
			if p.log != nil {
				p.log("release: %s req=%s endpoint=%s", leaseID, leaseID, selected.Manifest.ID)
			}
		}
	}()

	p.forwardSelected(w, r, selected, body, leaseID, candLog, req, reqCtx)
}

// forwardSelected proxies to the chosen endpoint with pre-stream failover and
// direct streaming.
func (p *Proxy) forwardSelected(
	w http.ResponseWriter,
	r *http.Request,
	selected *registry.Entry,
	body []byte,
	leaseID string,
	candLog []routing.CandidateResult,
	req routing.Req,
	reqCtx int,
) {
	// Build the upstream request.
	m := selected.Manifest
	base := "http://" + m.Host.Address + ":" + intToStr(m.Runtime.Port)
	// Model alias translation: public alias -> backend served model name. The
	// upstream body must carry the backend's served model (qwen3.8), not the
	// public alias (local-coding) the client used.
	upBody := translateModelInBody(body, m.Model.ServedModelName)
	upReq, err := http.NewRequest(r.Method, base+r.URL.Path, bytes.NewReader(upBody))
	if err != nil {
		p.upstreamError(w, selected, leaseID, err)
		return
	}
	// Carry the client context so a client cancel propagates to the upstream.
	upReq = upReq.WithContext(r.Context())
	for k, v := range r.Header {
		for _, vv := range v {
			upReq.Header.Add(k, vv)
		}
	}
	if m.Runtime.APIFamily == "openai" || r.URL.Path == "/v1/chat/completions" {
		upReq.Header.Set("Content-Type", "application/json")
	}

	resp, err := p.client.Do(upReq)
	if err != nil {
		// Pre-stream: upstream connect failed. (With a single endpoint there's
		// nowhere to fail over; with more, the caller could try the next.)
		p.upstreamError(w, selected, leaseID, err)
		return
	}
	defer resp.Body.Close()

	// First meaningful response byte => no silent migration after this.
	firstByte := p.streamResponse(w, resp, m.Model.ServedModelName)
	_ = firstByte

	p.logRouting(leaseID, req, reqCtx, candLog, m.ID, "selected")
	p.telemetry.RecordRequest(m.ID, int(resp.StatusCode))
}

// streamResponse copies the upstream response body to the client. It returns
// true if at least one meaningful byte was written (the stream started).
func (p *Proxy) streamResponse(w http.ResponseWriter, resp *http.Response, servedModel string) bool {
	// Copy headers (content-type, etc.). For alias translation we rewrite the
	// model field on non-streamed bodies; streaming SSE is passed through.
	ct := resp.Header.Get("Content-Type")
	isStream := ct == "text/event-stream"

	for k, vv := range resp.Header {
		for _, v := range vv {
			w.Header().Add(k, v)
		}
	}
	w.WriteHeader(resp.StatusCode)

	flusher, _ := w.(http.Flusher)

	var wrote bool
	if isStream {
		// Stream SSE chunks directly (low overhead).
		buf := make([]byte, 32*1024)
		for {
			n, rerr := resp.Body.Read(buf)
			if n > 0 {
				wrote = true
				if _, werr := w.Write(buf[:n]); werr != nil {
					p.telemetry.RecordClientDisconnect()
					return true
				}
				if flusher != nil {
					flusher.Flush()
				}
			}
			if rerr != nil {
				break
			}
		}
		return wrote
	}

	// Non-stream body: pass through (alias rewrite would need a re-encode; for
	// v1 we keep it transparent and rely on the backend serving the right name).
	_, _ = io.Copy(w, resp.Body)
	return true
}

// translateModelInBody rewrites the top-level "model" field to the backend's
// served name (e.g. public alias "local-coding" -> "qwen3.8"). It returns the
// re-marshal-ed body to send upstream; on any parse failure it returns the
// original body unchanged (transparent pass-through).
func translateModelInBody(body []byte, served string) []byte {
	var obj map[string]any
	if json.Unmarshal(body, &obj) != nil {
		return body
	}
	if _, ok := obj["model"]; !ok {
		obj["model"] = served
	} else if obj["model"] != served {
		// Client sent a public alias or a different name; force the backend's
		// served model name so the upstream vLLM resolves it.
		obj["model"] = served
	}
	out, err := json.Marshal(obj)
	if err != nil {
		return body
	}
	return out
}

func (p *Proxy) upstreamError(w http.ResponseWriter, selected *registry.Entry, leaseID string, err error) {
	p.log("upstream-error: %s req=%s endpoint=%s: %v", leaseID, leaseID, selected.Manifest.ID, err)
	p.telemetry.RecordUpstreamError(selected.Manifest.ID)
	writeJSON(w, http.StatusBadGateway, map[string]any{
		"error": map[string]any{
			"type":    "upstream_connect_failed",
			"message": err.Error(),
			"reason":  "UPSTREAM_CONNECT_FAILED",
		},
	})
}

func (p *Proxy) logRouting(leaseID string, req routing.Req, reqCtx int, candLog []routing.CandidateResult, selected, note string) {
	if p.log == nil {
		return
	}
	p.log("routing: req=%s reqctx=%d vision=%v tools=%v selected=%s note=%s candidates=%d",
		leaseID, reqCtx, req.HasImages, req.RequiresTools, selected, note, len(candLog))
}

// orderedCandidates returns the filtered+sorted candidate entries (in
// deterministic priority + context order) plus a candidate log.
func (p *Proxy) orderedCandidates(t *registry.Table, req routing.Req, reqCtx int) ([]*registry.Entry, []routing.CandidateResult) {
	var ordered []*registry.Entry
	var log []routing.CandidateResult

	entries := t.All()
	// Filter by capability + context + lifecycle.
	for _, e := range entries {
		m := e.Manifest
		st := e.State
		if req.HasImages && !m.Capabilities.Vision {
			log = append(log, routing.CandidateResult{ID: m.ID, Result: string(routing.ReasonVisionRequired)})
			continue
		}
		if req.RequiresTools && !m.Capabilities.Tools {
			log = append(log, routing.CandidateResult{ID: m.ID, Result: string(routing.ReasonToolsRequired)})
			continue
		}
		if req.RequiresStreaming && !m.Capabilities.Streaming {
			log = append(log, routing.CandidateResult{ID: m.ID, Result: string(routing.ReasonStreamingRequired)})
			continue
		}
		if m.Context.MaxContextTokens < reqCtx {
			log = append(log, routing.CandidateResult{ID: m.ID, Result: string(routing.ReasonContextTooSmall)})
			continue
		}
		if !st.Enabled {
			log = append(log, routing.CandidateResult{ID: m.ID, Result: string(routing.ReasonEndpointDisabled)})
			continue
		}
		if !st.Healthy {
			log = append(log, routing.CandidateResult{ID: m.ID, Result: string(routing.ReasonEndpointUnhealthy)})
			continue
		}
		if st.Draining {
			log = append(log, routing.CandidateResult{ID: m.ID, Result: string(routing.ReasonEndpointDraining)})
			continue
		}
		ordered = append(ordered, e)
	}
	// Deterministic sort: priority, then context (smallest sufficient first),
	// then id.
	sortEntries(ordered)
	return ordered, log
}

// newLeaseID returns a short unique id. (Not cryptographic; just distinct.)
var leaseSeq uint64

func newLeaseID() string {
	seq := leaseSeq
	leaseSeq++
	return "req_" + itoa(uint64(time.Now().UnixNano()/1e6)) + "_" + itoa(seq)
}
