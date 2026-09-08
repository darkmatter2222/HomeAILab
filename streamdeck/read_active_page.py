"""Read the current page of each Elgato Stream Deck profile via the profile-mode
streamdeck-mcp server.

Usage:
  python streamdeck/read_active_page.py
"""

import json
import sys

from fetch_state import McpStdioClient


def main() -> int:
    client = McpStdioClient(["streamdeck-mcp"])
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

        profiles_raw = client.call_tool("streamdeck_read_profiles")
        profiles = profiles_raw if isinstance(profiles_raw, list) else []

        for profile in profiles:
            name = profile.get("name")
            for page in profile.get("pages", []):
                if not page.get("is_current"):
                    continue
                page_data = client.call_tool(
                    "streamdeck_read_page",
                    {
                        "profile_id": profile.get("profile_id"),
                        "directory_id": page.get("directory_id"),
                    },
                )
                buttons = page_data.get("buttons", [])
                print(f"profile: {name} (page: {page.get('page_uuid')})")
                for b in buttons:
                    print(json.dumps(b, ensure_ascii=False))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
