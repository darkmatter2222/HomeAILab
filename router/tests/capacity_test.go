package tests

import (
	"sync"
	"testing"
	"time"

	"llm-router/internal/capacity"
)

// TestCapacityConcurrencyExactlyOne: 100 goroutines against a capacity-1 pool
// -> exactly one reserves, the rest get CAPACITY_FULL. No leak after release.
func TestCapacityConcurrencyExactlyOne(t *testing.T) {
	pool := capacity.NewPool("ep", 1, nil)
	const N = 100
	var (
		mu       sync.Mutex
		reserved int
		full     int
	)
	var wg sync.WaitGroup
	for i := 0; i < N; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			lease, ok := pool.Reserve("req_" + itoa(id))
			if ok {
				mu.Lock()
				reserved++
				mu.Unlock()
				// Hold briefly, then release.
				time.Sleep(5 * time.Millisecond)
				pool.Release("req_" + itoa(id))
				_ = lease
			} else {
				mu.Lock()
				full++
				mu.Unlock()
			}
		}(i)
	}
	wg.Wait()
	if reserved != 1 {
		t.Fatalf("expected exactly 1 reservation, got %d", reserved)
	}
	if pool.Inflight() != 0 {
		t.Fatalf("expected inflight 0 after all releases, got %d", pool.Inflight())
	}
	if full != N-1 {
		t.Fatalf("expected %d capacity_full, got %d", N-1, full)
	}
}

// TestLeaseReap: a leaked (unreleased) lease is reaped after the hard timeout.
func TestLeaseReap(t *testing.T) {
	var reaped []string
	var mu sync.Mutex
	pool := capacity.NewPool("ep", 2, func(ep, req string) {
		mu.Lock()
		reaped = append(reaped, req)
		mu.Unlock()
	})
	if _, ok := pool.Reserve("leaked"); !ok {
		t.Fatal("reserve failed")
	}
	// Reap with a 1s timeout, "now" 10s in the future -> lease is stale.
	n := pool.ReapLeases(time.Now().Add(10*time.Second), 1*time.Second)
	if n != 1 {
		t.Fatalf("expected 1 reaped lease, got %d", n)
	}
	if len(reaped) != 1 {
		t.Fatalf("expected onReap callback 1x, got %d", len(reaped))
	}
	if pool.Inflight() != 0 {
		t.Fatalf("expected inflight 0 after reap, got %d", pool.Inflight())
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b []byte
	for n > 0 {
		b = append([]byte{byte('0' + n%10)}, b...)
		n /= 10
	}
	return string(b)
}
