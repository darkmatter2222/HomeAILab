// Package registry owns the in-memory routing table. The control plane
// (discovery, health, admin) mutates the table by building a new immutable
// view and atomically swapping the pointer (RCU), so the hot data plane can
// read a stable view without per-request locking.
package registry

import (
	"sort"
	"sync/atomic"

	"llm-router/internal/capacity"
	"llm-router/internal/manifest"
)

// State is the live lifecycle of an endpoint, kept out of the immutable
// manifest so control-plane transitions don't require a table swap.
type State struct {
	Enabled   bool
	Healthy   bool
	HealthyNow bool // last health probe result
	Draining  bool
	// HealthFailures / HealthSuccesses are thresholds the health worker drives.
	HealthFailures  int
	HealthSuccesses int
}

// Entry is one schedulable endpoint: its manifest, its atomic capacity pool,
// and its live state.
type Entry struct {
	Manifest *manifest.Endpoint
	Pool     *capacity.Pool
	State    *State
}

// Table is an immutable snapshot of all endpoints. The Registry atomically
// swaps the whole *Table so readers see a consistent view.
type Table struct {
	endpoints map[string]*Entry
	// Precomputed capability indexes for O(1) candidate lookups.
	visionIDs  map[string]bool
	toolsIDs   map[string]bool
	streamIDs  map[string]bool
	byClass    map[string][]string // "64k","131k","262k" -> endpoint ids
	maxCtxByID map[string]int
}

// NewTable builds a table from endpoints, wiring each to a fresh capacity pool.
func NewTable(endpoints []manifest.Endpoint, onReap func(endpointID, requestID string)) *Table {
	t := &Table{
		endpoints: make(map[string]*Entry),
		visionIDs: make(map[string]bool),
		toolsIDs:  make(map[string]bool),
		streamIDs: make(map[string]bool),
		byClass:   map[string][]string{},
		maxCtxByID: make(map[string]int),
	}
	for i := range endpoints {
		e := endpoints[i]
		id := e.ID
		pool := capacity.NewPool(id, e.Routing.StaticCapacity, onReap)
		t.endpoints[id] = &Entry{
			Manifest: &e,
			Pool:     pool,
			State:    &State{Enabled: e.Enabled, Healthy: true},
		}
		t.maxCtxByID[id] = e.Context.MaxContextTokens
		if e.Capabilities.Vision {
			t.visionIDs[id] = true
		}
		if e.Capabilities.Tools {
			t.toolsIDs[id] = true
		}
		if e.Capabilities.Streaming {
			t.streamIDs[id] = true
		}
		if e.Context.ContextClass != "" {
			t.byClass[e.Context.ContextClass] = append(t.byClass[e.Context.ContextClass], id)
		}
	}
	return t
}

// Get returns an entry by id (nil if absent).
func (t *Table) Get(id string) *Entry { return t.endpoints[id] }

// All returns all entries (snapshot).
func (t *Table) All() []*Entry {
	out := make([]*Entry, 0, len(t.endpoints))
	for _, e := range t.endpoints {
		out = append(out, e)
	}
	return out
}

// IDs returns sorted endpoint ids (deterministic).
func (t *Table) IDs() []string {
	ids := make([]string, 0, len(t.endpoints))
	for id := range t.endpoints {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

// Healthy returns how many endpoints are currently healthy (for /health).
func (t *Table) HealthyCount() int {
	n := 0
	for _, e := range t.endpoints {
		if e.State.Healthy {
			n++
		}
	}
	return n
}

// Registry is the atomic holder of the current *Table. The control plane
// calls Set with a freshly built Table; the data plane calls View to get the
// current immutable snapshot.
type Registry struct {
	table atomic.Pointer[Table]
}

// NewRegistry builds an initial registry from the seed endpoints.
func NewRegistry(seeds []manifest.Endpoint, onReap func(endpointID, requestID string)) *Registry {
	r := &Registry{}
	r.table.Store(NewTable(seeds, onReap))
	return r
}

// View returns the current immutable table snapshot.
func (r *Registry) View() *Table { return r.table.Load() }

// Set atomically replaces the table (control plane: after discovery or an
// admin mutation).
func (r *Registry) Set(t *Table) { r.table.Store(t) }
