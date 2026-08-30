# ---- build stage ----
FROM golang:1.24 AS build
WORKDIR /src
# Cache module deps.
COPY go.mod go.sum ./
RUN go mod download
# Source.
COPY . .
# Static binary (CGO off).
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/llm-router ./cmd/router

# ---- runtime (scratch: no shell, no fs writes) ----
FROM scratch
COPY --from=build /out/llm-router /llm-router
# Non-root (the router only listens; no fs writes).
USER 65534:65534
# The healthcheck calls `llm-router health-probe` (no shell needed).
ENTRYPOINT ["/llm-router"]
