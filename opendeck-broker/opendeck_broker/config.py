"""Broker configuration.

All values can be overridden by environment variables so the same code runs in
CI (loopback, mock device) and on the desktop host (real Mini).
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .images import DEFAULT_KEY_SIZE
from .opencode.observe import default_db_path


def _token_path() -> Path:
    base = Path(os.environ.get("OPENDECK_BROKER_HOME", "")) if os.environ.get("OPENDECK_BROKER_HOME") else (
        Path.home() / ".local" / "state" / "opendeck-broker"
    )
    return base / "token"


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8899
    image_size: int = DEFAULT_KEY_SIZE
    db_path: Optional[os.PathLike] = None
    device_serial: Optional[str] = None
    heartbeat_seconds: float = 2.0
    lease_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            host=os.environ.get("OPENDECK_BROKER_HOST", "127.0.0.1"),
            port=int(os.environ.get("OPENDECK_BROKER_PORT", "8899")),
            image_size=int(os.environ.get("OPENDECK_KEY_SIZE", str(DEFAULT_KEY_SIZE))),
            db_path=os.environ.get("OPENCODE_DB") or None,
            device_serial=os.environ.get("OPENDECK_MINI_SERIAL") or None,
            heartbeat_seconds=float(os.environ.get("OPENDECK_HEARTBEAT_S", "2")),
            lease_seconds=float(os.environ.get("OPENDECK_LEASE_S", "10")),
        )

    def token(self) -> str:
        """Load the locally stored random token, creating it on first run. A
        press accepts a known instance id, not an arbitrary command, so the
        token only gates the loopback API."""
        p = _token_path()
        try:
            if p.exists():
                t = p.read_text().strip()
                if t:
                    return t
            p.parent.mkdir(parents=True, exist_ok=True)
            t = secrets.token_hex(16)
            p.write_text(t)
            try:
                p.chmod(0o600)
            except Exception:
                pass
            return t
        except Exception:
            return secrets.token_hex(16)

    def db(self) -> Path:
        return Path(self.db_path) if self.db_path else default_db_path()
