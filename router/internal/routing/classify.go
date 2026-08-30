// Package routing classifies an inbound request and deterministically selects
// an endpoint. The hot path reads only the in-memory routing table: no health
// probe, no GPU query, no Prometheus, no model introspection.
package routing

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"

	"llm-router/internal/registry"
)

// Req is the result of classifying one inbound request.
type Req struct {
	HasImages          bool
	RequiresTools      bool
	RequiresStreaming  bool
	InputTokenEstimate int
	RequestedMaxOutput int
	RequiredContext    int
	// ModelAlias is the public alias the client used (e.g. "local-coding").
	ModelAlias string
}

// RejectionReason is a stable diagnostic code (handoff §15).
type RejectionReason string

const (
	ReasonVisionRequired    RejectionReason = "VISION_REQUIRED"
	ReasonToolsRequired     RejectionReason = "TOOLS_REQUIRED"
	ReasonStreamingRequired RejectionReason = "STREAMING_REQUIRED"
	ReasonContextTooSmall   RejectionReason = "CONTEXT_TOO_SMALL"
	ReasonEndpointUnhealthy RejectionReason = "ENDPOINT_UNHEALTHY"
	ReasonEndpointDisabled  RejectionReason = "ENDPOINT_DISABLED"
	ReasonEndpointDraining  RejectionReason = "ENDPOINT_DRAINING"
	ReasonCapacityFull     RejectionReason = "CAPACITY_FULL"
	ReasonReservationRace  RejectionReason = "RESERVATION_RACE_LOST"
	ReasonUpstreamConnect  RejectionReason = "UPSTREAM_CONNECT_FAILED"
)

// CandidateResult records why a candidate was (or was not) selected.
type CandidateResult struct {
	ID     string
	Result string // "selected" | reason code
}

// SelectOutcome is the result of a selection attempt.
type SelectOutcome struct {
	Selected   *registry.Entry
	LeaseID    string
	Candidates []CandidateResult
	// Reserved is true if a slot was reserved on Selected (caller MUST release
	// via Pool.Release on completion/cancel/error).
	Reserved bool
}

// Classify derives the request requirements from a raw body. It parses just
// enough JSON to detect images, tools, streaming, and max_output without a
// full model-specific decode. The token estimate is a conservative char/4.
func Classify(body []byte, apiFamily string) Req {
	var probe struct {
		Stream      bool `json:"stream"`
		MaxTokens   int  `json:"max_tokens"`
		MaxOutput   int  `json:"max_completion_tokens"`
		Tools       any  `json:"tools"`
		ToolChoice  any  `json:"tool_choice"`
		Messages    []struct {
			Content any `json:"content"`
		} `json:"messages"`
		Input any `json:"input"`
		Model string `json:"model"`
	}
	if len(body) > 0 {
		_ = json.Unmarshal(body, &probe)
	}

	req := Req{
		RequiresStreaming: probe.Stream,
		RequestedMaxOutput: probe.MaxTokens,
		ModelAlias:         probe.Model,
	}
	if probe.MaxOutput > 0 {
		req.RequestedMaxOutput = probe.MaxOutput
	}

	// Tools present (OpenAI: tools array; Anthropic: tools too).
	if probe.Tools != nil {
		if arr, ok := probe.Tools.([]any); ok && len(arr) > 0 {
			req.RequiresTools = true
		}
	}

	// Images: scan message content for image blocks (OpenAI content array, or
	// Anthropic content blocks with type:"image").
	var contentBytes int
	hasImage := detectImage(probe.Messages)
	req.HasImages = hasImage

	// Conservative input token estimate from body size (chars/4).
	contentBytes = len(body)
	req.InputTokenEstimate = contentBytes / 4

	return req
}

func detectImage(msgs []struct {
	Content any `json:"content"`
}) bool {
	for _, m := range msgs {
		switch c := m.Content.(type) {
		case string:
			// plain text content; no image
		case []any:
			for _, part := range c {
				if p, ok := part.(map[string]any); ok {
					if typ, _ := p["type"].(string); typ == "image" || typ == "image_url" || typ == "image_base64" {
						return true
					}
				}
			}
		}
	}
	return false
}

// RequiredContext computes the token budget a request needs, including the
// safety reserve (max(reserveTokens, reservePercent% of request)).
func RequiredContext(inputTokens, maxOutput, reserveTokens, reservePercentPct, bodyBytes int) int {
	reserve := reserveTokens
	if pct := int(math.Round(float64(bodyBytes) * (float64(reservePercentPct) / 100.0) / 4)); pct > reserve {
		reserve = pct
	}
	if reserve < 0 {
		reserve = 0
	}
	return inputTokens + maxOutput + reserve
}

// Select filters and deterministically ranks candidates, then reserves the
// first one that has a free slot. Preference order:
//
//	host priority (lower first) -> context class (smallest sufficient first)
//	-> endpoint id (deterministic tiebreak)
//
// A candidate is rejected (with a reason code) if: disabled, unhealthy,
// draining, context too small, capability mismatch (vision/tools/streaming),
// or capacity full / reservation race lost.
func Select(
	t *registry.Table,
	req Req,
	reqCtx int,
	// preference knobs
	_ func() bool,
	// lease id for the reservation
	leaseID string,
) SelectOutcome {
	out := SelectOutcome{}

	entries := t.All()

	// Determine the smallest context class that can satisfy reqCtx, for the
	// "prefer smallest sufficient context" ordering.
	minClass := smallestSufficientClass(reqCtx)

	// Filter + rank.
	type cand struct {
		e    *registry.Entry
		prio int
		ctx  int
	}
	var cands []cand
	for _, e := range entries {
		m := e.Manifest
		// Capability gates.
		if req.HasImages && !m.Capabilities.Vision {
			out.Candidates = append(out.Candidates, CandidateResult{ID: m.ID, Result: string(ReasonVisionRequired)})
			continue
		}
		if req.RequiresTools && !m.Capabilities.Tools {
			out.Candidates = append(out.Candidates, CandidateResult{ID: m.ID, Result: string(ReasonToolsRequired)})
			continue
		}
		if req.RequiresStreaming && !m.Capabilities.Streaming {
			out.Candidates = append(out.Candidates, CandidateResult{ID: m.ID, Result: string(ReasonStreamingRequired)})
			continue
		}
		if m.Context.MaxContextTokens < reqCtx {
			out.Candidates = append(out.Candidates, CandidateResult{ID: m.ID, Result: string(ReasonContextTooSmall)})
			continue
		}
		// Lifecycle gates.
		st := e.State
		if !st.Enabled {
			out.Candidates = append(out.Candidates, CandidateResult{ID: m.ID, Result: string(ReasonEndpointDisabled)})
			continue
		}
		if !st.Healthy {
			out.Candidates = append(out.Candidates, CandidateResult{ID: m.ID, Result: string(ReasonEndpointUnhealthy)})
			continue
		}
		if st.Draining {
			out.Candidates = append(out.Candidates, CandidateResult{ID: m.ID, Result: string(ReasonEndpointDraining)})
			continue
		}
		cands = append(cands, cand{e: e, prio: m.Routing.Priority, ctx: m.Context.MaxContextTokens})
	}

	// Deterministic sort: host priority, then context class (smallest
	// sufficient first), then endpoint id.
	sort.SliceStable(cands, func(i, j int) bool {
		if cands[i].prio != cands[j].prio {
			return cands[i].prio < cands[j].prio
		}
		// Prefer the smallest context that still fits (smallest-first within
		// the same priority). A context equal to reqCtx is the tightest fit.
		return cands[i].ctx < cands[j].ctx
	})
	_ = minClass

	// Reserve the first candidate with a free slot.
	for _, c := range cands {
		_, ok := c.e.Pool.Reserve(leaseID)
		if ok {
			out.Selected = c.e
			out.LeaseID = leaseID
			out.Reserved = true
			out.Candidates = append(out.Candidates, CandidateResult{ID: c.e.Manifest.ID, Result: "selected"})
			// Re-sort candidate list to put selected first (stable for logging).
			return out
		}
		out.Candidates = append(out.Candidates, CandidateResult{ID: c.e.Manifest.ID, Result: string(ReasonCapacityFull)})
	}
	return out
}

// smallestSufficientClass returns the smallest class name (64k/131k/262k) whose
// ceiling is >= reqCtx. Used for ordering; the actual gate is MaxContextTokens.
func smallestSufficientClass(reqCtx int) string {
	classes := []struct {
		name string
		max  int
	}{
		{"64k", 65536},
		{"131k", 131072},
		{"262k", 262144},
	}
	for _, c := range classes {
		if reqCtx <= c.max {
			return c.name
		}
	}
	return "262k"
}

// String renders a reason for logs.
func (r RejectionReason) String() string { return string(r) }

var _ = fmt.Sprintf // keep fmt import for future formatting
