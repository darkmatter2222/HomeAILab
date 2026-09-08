"""Fetch the live on-screen state of an Elgato Stream Deck via the streamdeck-mcp MCP server.

Uses the streamdeck-mcp server (verygoodplugins/streamdeck-mcp) in USB-direct
mode (streamdeck-mcp-usb). No screenshot of the Stream Deck software is taken;
state is read over USB/HID through the MCP tool API.

MCP tool sequence:
  streamdeck_list_devices  -> which decks are attached
  streamdeck_connect       -> open the deck over USB
  streamdeck_info          -> model, key grid, firmware, current page, brightness
  streamdeck_list_pages    -> page list + current page
  streamdeck_get_button    -> per-key on-screen state (label/image, colors, action)

Goal alignment (MCPN API / Python test automation):
  This script is one of the existing Python scripts for interacting with the
  MCPN API. It inspects device state where supported (USB readback of the
  live on-screen state), captures button state (streamdeck_get_button per key),
  validates button contents (label/image, colors, action), and the acceptance
  harness (acceptance.py) reuses its McpStdioClient + fetch_state to compare
  expected and actual state, timestamp state transitions, collect evidence,
  and repeatedly execute regression tests.

Usage:
  python streamdeck/fetch_state.py
  python streamdeck/fetch_state.py --serial <serial>
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time


def default_command() -> list[str]:
    override = os.environ.get("STREAMDECK_MCP_CMD")
    if override:
        return override.split()
    return ["uvx", "--from", "streamdeck-mcp", "streamdeck-mcp-usb"]


class McpStdioClient:
    """Minimal MCP stdio JSON-RPC 2.0 client (newline-delimited messages)."""

    def __init__(self, command: list[str]):
        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._next_id = 0
        self._pending: dict[int, dict] = {}
        self._lock = threading.Lock()
        self.stderr = ""
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self) -> None:
        for line in self.proc.stdout:
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                with self._lock:
                    self._pending[msg["id"]] = msg

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def request(self, method: str, params: dict | None = None, timeout: float = 60.0) -> dict:
        self._next_id += 1
        rid = self._next_id
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        deadline = time.time() + timeout
        while True:
            with self._lock:
                resp = self._pending.pop(rid, None)
            if resp is not None:
                if "error" in resp:
                    err = resp["error"]
                    raise RuntimeError(f"MCP error in {method}: {err.get('message', err)}")
                return resp.get("result") or {}
            if time.time() > deadline:
                raise TimeoutError(f"MCP server did not answer {method} within {timeout:.0f}s")
            time.sleep(0.05)

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content") or []
        text = next((c.get("text", "") for c in content if c.get("type") == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
            self.proc.wait(timeout=5)
        try:
            self.stderr = self.proc.stderr.read().decode("utf-8", errors="replace").strip()
        except Exception:
            self.stderr = ""


def parse_pages(raw: dict) -> dict:
    text = raw.get("raw", "")
    lines = [ln.strip() for ln in text.splitlines()]
    pages: list[str] = []
    current: str | None = None
    for line in lines:
        if not line or line == "Pages:":
            continue
        if line.startswith("\u2192"):
            current = line[1:].strip()
            pages.append(current)
        else:
            pages.append(line)
    return {"pages": pages, "current": current}


def fetch_state(serial: str | None = None) -> tuple[dict, McpStdioClient]:
    client = McpStdioClient(default_command())
    try:
        client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "homeailab-streamdeck-state", "version": "1.0"},
            },
        )
        client.notify("notifications/initialized")

        devices = client.call_tool("streamdeck_list_devices")
        connect_args = {"serial": serial} if serial else None
        connect = client.call_tool("streamdeck_connect", connect_args)
        deck = client.call_tool("streamdeck_info")
        pages_raw = client.call_tool("streamdeck_list_pages")

        if isinstance(devices, dict) and "Unknown tool" in str(devices.get("raw", "")):
            if deck.get("connected"):
                devices = [
                    {
                        "serial": deck.get("serial"),
                        "deck_type": deck.get("type"),
                        "key_count": deck.get("key_count"),
                    }
                ]
            else:
                devices = []

        key_count = int(deck.get("key_count") or 0)
        keys = [client.call_tool("streamdeck_get_button", {"key": key}) for key in range(key_count)]

        state = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "devices": devices if isinstance(devices, list) else [devices],
            "connect": connect,
            "deck": deck,
            "pages": parse_pages(pages_raw),
            "screen": {
                "page": deck.get("current_page"),
                "keys": keys,
            },
        }
        return state, client
    except Exception:
        client.close()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull Stream Deck on-screen state via streamdeck-mcp")
    parser.add_argument("--serial", help="Stream Deck serial from streamdeck_list_devices")
    args = parser.parse_args()

    try:
        state, client = fetch_state(args.serial)
        client.close()
    except FileNotFoundError as e:
        print(json.dumps({"error": "MCP server command not found", "detail": str(e)}, indent=2))
        return 1
    except (RuntimeError, TimeoutError) as e:
        print(json.dumps({"error": str(e)}, indent=2))
        return 1
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {e}"}, indent=2))
        return 1

    out = json.dumps(state, indent=2, ensure_ascii=False)
    sys.stdout.buffer.write(out.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
