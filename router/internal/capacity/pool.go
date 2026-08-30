// Package capacity holds the atomic static-capacity model. Each endpoint owns
// a Pool: a compare-and-increment reserve, a lease map for watchdog repair,
// and a release that is guaranteed to run exactly once per request.
package capacity

import (
	"sync"
	"sync/atomic"
	"time"
)

// Lease is a single in-flight reservation record. The control-plane watchdog
// reaps leases older than the hard timeout so a crashed request cannot leak a
// slot forever.
type Lease struct {
	RequestID     string
	StartedAt     time.Time
	LastActivity  time.Time
}

// Pool is the per-endpoint atomic capacity counter + lease map.
//
// Reserve is a compare-and-increment: if inflight < cap, increment and record
// a lease atomically (the caller holding the returned lease is the owner). If
// the capacity is full, Reserve returns ok=false and the caller must try the
// next candidate endpoint. Release is idempotent and safe to call from a
// defer.
type Pool struct {
	capacity int
	inflight atomic.Int64
	mu       sync.Mutex
	leases   map[string]*Lease
	// onReap is an optional callback (control-plane logging/metrics).
	onReap func(endpointID, requestID string)
	// endpointID is stamped into the lease for observability.
	endpointID string
}

// NewPool creates a pool with the given static capacity. hardTimeout is the
// lease lease; <=0 disables reaping (the watchdog is control-plane only).
// onReap may be nil.
func NewPool(endpointID string, staticCapacity int, onReap func(endpointID, requestID string)) *Pool {
	if staticCapacity < 1 {
		staticCapacity = 1
	}
	return &Pool{
		capacity:   staticCapacity,
		leases:     make(map[string]*Lease),
		onReap:     onReap,
		endpointID: endpointID,
	}
}

// Reserve atomically reserves one slot. Returns the lease on success.
func (p *Pool) Reserve(requestID string) (*Lease, bool) {
	for {
		cur := p.inflight.Load()
		if cur >= int64(p.capacity) {
			return nil, false // CAPACITY_FULL
		}
		if p.inflight.CompareAndSwap(cur, cur+1) {
			break
		}
	}
	now := time.Now()
	lease := &Lease{RequestID: requestID, StartedAt: now, LastActivity: now}
	p.mu.Lock()
	p.leases[requestID] = lease
	p.mu.Unlock()
	return lease, true
}

// Release frees the slot reserved under requestID. Idempotent.
func (p *Pool) Release(requestID string) {
	p.mu.Lock()
	_, exists := p.leases[requestID]
	if exists {
		delete(p.leases, requestID)
	}
	p.mu.Unlock()
	if exists {
		p.inflight.Add(-1)
	}
}

// Touch refreshes a lease's last-activity time (used by a streaming proxy to
// prove the request is still live, delaying the watchdog).
func (p *Pool) Touch(requestID string) {
	p.mu.Lock()
	if l, ok := p.leases[requestID]; ok {
		l.LastActivity = time.Now()
	}
	p.mu.Unlock()
}

// Inflight returns the current in-flight count.
func (p *Pool) Inflight() int64 { return p.inflight.Load() }

// Capacity returns the static capacity.
func (p *Pool) Capacity() int { return p.capacity }

// Available returns how many slots are free right now.
func (p *Pool) Available() int64 {
	avail := int64(p.capacity) - p.inflight.Load()
	if avail < 0 {
		avail = 0
	}
	return avail
}

// ReapLeases evicts leases whose last-activity is older than hardTimeout.
// It is a control-plane operation and must not be called from the hot path.
// Returns the number of reaped leases.
func (p *Pool) ReapLeases(now time.Time, hardTimeout time.Duration) int {
	if hardTimeout <= 0 {
		return 0
	}
	cutoff := now.Add(-hardTimeout)
	p.mu.Lock()
	var reaped []string
	for id, l := range p.leases {
		if l.LastActivity.Before(cutoff) {
			reaped = append(reaped, id)
			delete(p.leases, id)
		}
	}
	p.mu.Unlock()
	for _, id := range reaped {
		p.inflight.Add(-1)
		if p.onReap != nil {
			p.onReap(p.endpointID, id)
		}
	}
	return len(reaped)
}
