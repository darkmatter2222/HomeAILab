# Local broker protocol

Endpoint: `http://127.0.0.1:<discovery.port>`. `.opencode-deck/discovery.json` is atomically written after socket binding and removed on graceful shutdown. The token is in a separate per-user `token` file. Never print it into logs or commit it.

Every request requires `Authorization: Bearer <token>`. JSON bodies must be objects, at most 64 KiB. Browser Origin headers are refused. This is a trusted local application protocol, not an exposed LAN service. Clients reread discovery and token rather than assuming the port persists.

| Method | Path | Meaning |
|---|---|---|
| GET | `/v1/status` | Broker epoch, device health, slots, overflow count, last focus result |
| POST | `/v1/register` | Create or renew a matching immutable process identity |
| PUT | `/v1/instances/{id}` | Newer complete normalized snapshot |
| DELETE | `/v1/instances/{id}` | Detach; release slot |
| POST | `/v1/focus` | Synthetic focus request for an existing assignment |
| POST | `/v1/stop` | Graceful broker shutdown |

Registration:

```json
{"id":"unique-launch-uuid","process":{"pid":1234,"created":1770000000.123},"label":"HomeAILab","windowToken":"OpenCode [unique-launch-uuid]"}
```

The timestamp is `psutil.Process(pid).create_time()`, not a guessed epoch. The broker rejects a process that is not alive locally. Re-registering the same ID with a different identity is rejected. Process presence renewals do not turn stale state into current state.

Snapshot:

```json
{"producer":"fresh-plugin-uuid","seq":42,"status":"busy","pending":1,"detail":""}
```

Status accepts idle, busy, retry, unknown. Pending is a nonnegative count of unresolved request IDs maintained in the producer. Monotonic sequences apply within a producer epoch. Superseded producer epochs are retired; their delayed messages are ignored. A new broker starts empty and asks clients to re-register through ordinary retries.

Focus payload is the assignment returned in `slots`, including `slot` (zero-based), `id`, and `generation`. CLI `ocdeck focus 1` uses user-facing one-based numbering and sends that exact tuple. It marks results `synthetic: true`. Physical callback requests are marked false. This distinction is retained in diagnostics.

HTTP 401 means missing credentials; 403 means a browser Origin was provided; 400 indicates invalid payload/process identity; 404 means unknown route/instance and clients should register again; 413 means excessive body size. State transitions come from snapshots only, not from the focus endpoint.
