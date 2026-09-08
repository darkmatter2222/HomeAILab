# OpenCode <-> Stream Deck Acceptance Test Report
Generated: 2026-09-04T23:40:11

## Results

| Test Case | Result |
|---|---|
| TC-001 | PASS |
| TC-002 | PASS |
| TC-003 | PASS |
| TC-004 | PASS |
| TC-005 | PASS |
| TC-006 | PASS |
| TC-007 | PASS |
| TC-008 | PASS |
| TC-009 | PASS |
| TC-010 | PASS |
| TC-011 | PASS |
| TC-012 | PASS |
| TC-013 | PASS |
| TC-020 | PASS |
| TC-021 | PASS |
| TC-022 | PASS |
| TC-023 | PASS |
| TC-024 | PASS |
| TC-030 | PASS |
| TC-031 | PASS |
| TC-032 | PASS |
| TC-033 | PASS |
| TC-034 | PASS |
| TC-040 | PASS |
| TC-041 | PASS |
| TC-050 | PASS |
| TC-051 | PASS |
| TC-052 | PASS |
| TC-053 | PASS |
| TC-054 | PASS |

**30/30 passed**

## Latency samples

- TC-002 session=xy6VVo8N detector_latency_ms=7039
- TC-004 session=H2WCsrpA detector_latency_ms=5962
- TC-005 session=hCq9Smdw detector_latency_ms=22524

## Reliability summary

- Total acceptance test cases: 30
- Passed: 30
- Failed: 0 (none)
- TC-041 stress repeats: 3
- Intermittent failures: none observed across repeated runs

## Latency distribution

- Samples: 3
- min=5962 ms, max=22524 ms, avg=11841 ms

## Known limitations

- USB readback (`mcp_deck_state`) is coarse: an OFF key often reads "unknown" rather than "off", so deck_state is treated as a supporting, not primary, evidence.
- Physical validation uses a screenshot of the Stream Deck app mirror (device mirror), sampling every Nth pixel; it confirms the on-device display but is a proxy for the physical LCD.
- TC-053 (device reconnect) is simulated via an app restart because a physical USB replug is not automatable.