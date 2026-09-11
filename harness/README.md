# harness/ - agent boot launchers

Global boot files for the agent harness (Claude Code, OpenCode, Copilot).
Copied from `C:\Users\ryans\bin` and sanitized for commit: every LAN IP and
the router API key now come from `.env` instead of being hard-coded. The
originals in `C:\Users\ryans\bin` still work standalone.

## Layout (by harness)

```
harness/
  load-env.bat            shared .env loader (called by every launcher)
  .env.example            placeholder subset (only needed without the root .env)
  claude/                 Claude Code launchers
  opencode/               OpenCode launchers
  copilot/                Copilot launchers
```

## .env mechanism

Every launcher calls `load-env.bat` right after `setlocal`. The loader:

1. Looks for `.env` in `harness\`, then in the repo root (`HomeAILab\.env`).
2. Parses `KEY=VALUE` lines (skips `#` comments, strips inline ` # comment`
   tails).
3. Writes them to a temp `.bat` and `call`s it, so the variables land in the
   launcher's environment.

The repo-root `.env` already defines every variable the launchers use, so no
extra file is needed when it exists. Without it, copy `.env.example` to
`harness\.env`. Both `.env` files are gitignored.

Variables used by the launchers:

| Variable        | Meaning                                    |
|-----------------|--------------------------------------------|
| `HOST_3090`     | Databrick RTX 3090 LAN IP (llama.cpp)      |
| `HOST_5090`     | RedPCv2 RTX 5090 LAN IP (vLLM)             |
| `HOST_DGXSPARK` | DGX Spark LAN IP (vision / vLLM)           |
| `ROUTER_API_KEY`| Go router key, used as the Anthropic token |

## claude/

| File                | Target                                                        |
|---------------------|---------------------------------------------------------------|
| `claude-cluster.bat`| Go router on Databrick :8001 (normal fleet path)              |
| `claude-3090.bat`   | Direct 3090 llama.cpp :8101, auto-detect, 262K ctx, thinking off |
| `claude-5090.bat`   | Direct 5090 vLLM :8201 (router bypass), 262K ctx, thinking off |
| `claude-spark.bat`  | Direct DGX Spark vision :8401, auto-detect                    |
| `claude-db.bat`     | Databrick vLLM :8006 (fixed URL, no auto-detect)              |
| `claude-dgx.bat`    | DGX Spark vLLM :8006 (fixed URL, no auto-detect)              |
| `claude-llama.bat`  | Local llama.cpp 127.0.0.1:8000, per-slot context from /slots  |
| `claude_llama.bat`  | Byte-identical duplicate of `claude-llama.bat`                |
| `claude-local.bat`  | Local vLLM 127.0.0.1:8006                                     |

## opencode/

| File                     | Target                                                        |
|--------------------------|---------------------------------------------------------------|
| `opencode-3090.bat`      | Direct 3090 llama.cpp, auto-detect + model discovery, builds an isolated temp OpenCode config |
| `opencode-3090-serve.bat`| Headless variant: `opencode serve --port 4096` for the Stream Deck bridge / `opencode attach` |
| `opencode-5090.bat`      | Direct 5090 vLLM :8201 (router bypass)                        |
| `opencode-5090-vision.bat`| Direct 5090 vLLM, 131K ctx, thinking on, vision enabled      |
| `opencode-spark.bat`     | Direct DGX Spark SGLang :8420 (Flash-Next NVFP4, vision ON)   |

## copilot/

| File             | Target                                  |
|------------------|------------------------------------------|
| `copilot-db.bat` | Databrick vLLM :8006/v1                  |
| `copilot-dgx.bat`| DGX Spark vLLM :8006/v1                  |

## Notes

- `local-*` auth tokens (`local-3090`, `local-vllm`, ...) are placeholders for
  backends that run without API-key enforcement; they are not secrets.
- Host machine names (Databrick, RedPCv2, dgxspark) appear in comments and
  status banners only; the IPs themselves are in `.env`.
- Port contracts (8100-8199 llama.cpp, 8200-8299 vLLM, 8400-8499 vision,
  8000-8009 router) are documented in `AGENTS.md`.
