package proxy

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"strconv"

	"llm-router/internal/registry"
	"llm-router/internal/routing"
)

// writeJSON writes a JSON object with the given status.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// intToStr renders an int as a string (for URL building).
func intToStr(n int) string { return strconv.Itoa(n) }

// sortEntries orders candidate entries deterministically: priority (lower
// first), then context (smallest sufficient first), then id (stable tiebreak).
func sortEntries(es []*registry.Entry) {
	sort.SliceStable(es, func(i, j int) bool {
		a, b := es[i], es[j]
		if a.Manifest.Routing.Priority != b.Manifest.Routing.Priority {
			return a.Manifest.Routing.Priority < b.Manifest.Routing.Priority
		}
		if a.Manifest.Context.MaxContextTokens != b.Manifest.Context.MaxContextTokens {
			return a.Manifest.Context.MaxContextTokens < b.Manifest.Context.MaxContextTokens
		}
		return a.Manifest.ID < b.Manifest.ID
	})
}

// itoa is a uint64->string helper for lease id building.
func itoa(n uint64) string { return strconv.FormatUint(n, 10) }

// candidateStrings flattens a candidate log into result-code strings for the
// (bounded-label) telemetry counter.
func candidateStrings(c []routing.CandidateResult) []string {
	out := make([]string, 0, len(c))
	for _, r := range c {
		out = append(out, r.Result)
	}
	return out
}

var _ = fmt.Sprintf
