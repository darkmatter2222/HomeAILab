# OpenCode Deck — Stream Deck plugin for your local OpenCode fleet

Turns an Elgato Stream Deck (Mini, 6 keys) into a live notification bar for your
local **OpenCode** agents. Each project gets **one key** showing that agent's
**real-time RAG state**, and pressing it focuses that session's terminal.

This is strictly **OpenCode → Stream Deck**: the plugin only *reads* OpenCode's
session state and *launches* your existing `opencode-3090-serve.bat`. It never
touches the models or the backends.

```
MINI (6 keys, 2 rows x 3 cols)
MAIN PAGE
  ┌─────────┬─────────┬─────────┐
  │ homeai   │ ryans    │ +      │
  │ ●RUNNING │ ●IDLE    │ spare  │
  ├─────────┼─────────┼─────────┤
  │ home_llm │ +      │ +      │
  │ ●IDLE    │ spare  │ spare  │
  └─────────┴─────────┴─────────┘
```

## What a key shows

One key per agent (working directory), up to 6 (the Mini's capacity). The state is
that agent's **most recently active session**, not a rotation across sessions:

| State | Colour | Meaning |
|---|---|---|
| `running` | green `#2fd06f` | opencode is actively generating / running a tool |
| `idle` | amber `#f5b13d` | alive but quiet |
| `waiting` | red `#ff5a4e` | opencode is asking a question / needs input |
| `off` | gray `#5a5e6b` | no connected opencode env / no session |

Press a key → the session's terminal comes to the front.

## How it sees OpenCode (two read-only sources)

The deck merges two sources of truth, then collapses them **1:1 per agent**:

1. **Global SQLite store** — `~/.local/share/opencode/opencode.db`. This is where
   OpenCode persists *all* sessions, including TUI sessions launched from a terminal
   (e.g. a bare `opencode` launch). The `serve` HTTP API does **not** list TUI
   sessions, which is why a terminal-launched agent "did not show up". The plugin
   shells out to the `sqlite3` CLI to read recent (last 90s) sessions.
2. **`opencode serve` HTTP API** — `GET /session` + `GET /session/status`, which
   carries the explicit per-session status (`busy`/`waiting`/`idle`). If the
   configured URL is unreachable, the deck falls back to the known serve ports
   (4096, 4202) so it tracks whichever `opencode serve` instance is actually live.

`collectSessions()` merges both by session id (server records win on explicit status);
`agentStates()` then keeps only the **most recently updated session per directory** —
that single record is the agent's real-time state. So one running agent shows exactly
**one** lit key, not several.

## How the plugin process is wired

- Stream Deck launches `bin/plugin.mjs` with single-dash args
  (`-port`, a per-launch `-pluginUUID` hash, `-registerEvent`, `-info` JSON).
- The plugin connects back over a loopback WebSocket, registers with the host's
  register event, and receives `willAppear` / `keyDown` / `didReceiveSettings`.
- A 5-second poller (`POLL_MS = 5_000`) drives `poll()`, which calls
  `collectSessions()` → `agentStates()` → `renderAll()`, pushing a RAG-coloured SVG
  key image per key via `setImage`.
- A 700ms breathing loop re-renders only while any agent is `running` or `waiting`.

## Press-to-focus / launch

- A single press on a project key calls `focusSession()` to raise the session's
  terminal window (title-marker match). A double-tap launches a second concurrent
  agent in the same project.
- When a project has **no live session**, pressing it calls `launchProject()`, which
  opens a Windows Terminal tab running the project's launcher (`bat`). The launch
  command is issued as `cmd /k "title <marker> opencode & <bat>"` so the tab's title
  carries a stable marker that focus matches on. This replaces the earlier
  PowerShell `-Command` form, whose arguments got mangled when passed through `wt`
  and produced **error 2147942402 (0x80070002) "The system cannot find the file
  specified."** Using `cmd /k` keeps the whole command as one quoted argument, so
  the launch succeeds.

## Config

`opendeck/projects.json` — the OpenCode server root plus one entry per project:

```json
{
  "opencode": { "url": "http://127.0.0.1:4096" },
  "projects": [
    { "alias": "homeai",
      "path": "C:/Users/ryans/source/repos/HomeAILab",
      "bat": "C:/Users/ryans/bin/opencode-3090-serve.bat" },
    { "alias": "ryans",
      "path": "C:/Users/ryans",
      "bat": "C:/Users/ryans/bin/opencode-3090-serve.bat" }
  ]
}
```

Sessions whose directory matches no configured project are auto-detected and minted
into `projects.auto.json` (never clobbers your hand-written file).

## Build / deploy / verify

```
cd opendeck
npm install
npm run build      # bundle src/ -> dev.ryans.opendeck.streamDeckPlugin/bin/plugin.mjs + rasterize icons
npm test           # 19 unit tests (node:test)
npm run selftest   # smoke-run the render path
```

**Deploy (local):** copy `dev.ryans.opendeck.streamDeckPlugin/` into
`%APPDATA%\Elgato\StreamDeck\Plugins\dev.ryans.opendeck.sdPlugin`, then restart
Stream Deck. (The deployed folder uses the `.sdPlugin` suffix, matching every other
plugin on this machine; a `.streamDeckPlugin` zip is the *distributable* form for
import/URL install.)

**Verify:** `node tools/probe-deck.mjs` walks Stream Deck's loopback ports and
confirms the plugin's registration handshake. It also reads the live plugin's
per-launch `-pluginUUID` hash so the probe registers exactly like the plugin. A
`CONFIRMED: plugin is live on the device` line means the plugin is running and
connected.

## Files

| File | What it is |
|---|---|
| `src/plugin.js` | I/O shell: WebSocket to Stream Deck, keyDown router, 5s poller, page mgmt |
| `src/sessions.js` | DB + serve polling, session mapping, RAG state, 1:1 `agentStates` |
| `src/config.js` | load/merge projects.json + projects.auto.json, opencode URL, sqlite3/DB resolution |
| `src/keyart.js` | pure 144x144 SVG key renderers (RAG colours) |
| `src/focus.js` | launch a terminal (`cmd /k`) + raise a session's window by title marker |
| `src/render.js` | map page/state -> the set of key images to push |
| `pi/pi.html` | property inspector (per-key label/color/path/bat) |
| `projects.json` | your projects + opencode server URL |
| `tools/probe-deck.mjs` | confirm the plugin is live on the device |
| `tools/livecheck.mjs` | dump current 1:1 agent states end-to-end |

Set `DFDECK_DEBUG=1` to see the plugin log to stderr.
