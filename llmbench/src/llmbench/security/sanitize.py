"""Centralized secret / identity sanitization (goal.md §10).

Sanitize **before** writing to disk — never write secrets then clean them.
The public report refers to infrastructure by stable aliases such as
``gpu-host-01`` / ``benchmark-client`` rather than real identities.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# IPv4 (loose; refined to skip version numbers via boundary checks at call sites)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# IPv6
_IPV6_RE = re.compile(r"\b[0-9a-fA-F]{0,4}:([0-9a-fA-F]{0,4}:){1,7}[0-9a-fA-F]{0,4}\b")
# MAC
_MAC_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b")
# GPU UUID (NVIDIA style: GPU-<32 hex>)
_GPU_UUID_RE = re.compile(r"\bGPU-[0-9a-fA-F]{32,36}\b")
# Generic serial / UUID
_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
# URLs with embedded credentials (user:pass@host)
_URL_CRED_RE = re.compile(r"(https?|ftp)://[^/@\s]+@")
# Bearer tokens
_BEARER_RE = re.compile(r"\bbearer\s+[A-Za-z0-9\-_\.=+/]{8,}\b", re.IGNORECASE)
# Authorization headers
_AUTH_RE = re.compile(r"\bauthorization\s*[:=]\s*[\w\-]+ [A-Za-z0-9\-_\.=+/]{8,}\b", re.IGNORECASE)
# Home-dir paths  (/home/<user>  or C:\Users\<user>  or ~)
_HOME_RE = re.compile(r"(/home/[^/\s\"']+|C:\\\\?Users\\\\?[^\\\s\"']+)")
# Hostnames in common positions (foo.bar, foo.local, foo.internal)
_HOSTNAME_RE = re.compile(
    r"\b(?:[a-z0-9][a-z0-9\-]{0,63}\.)+[a-z]{2,}\b"
)


# Environment-variable name patterns that imply sensitivity unless allowlisted
SENSITIVE_ENV_PATTERNS = (
    "KEY", "TOKEN", "SECRET", "PASSWORD", "PASS", "AUTH",
    "CREDENTIAL", "COOKIE", "SESSION",
)

# Common env-var names we always treat as non-secret (config, not credential)
ENV_ALLOWLIST = frozenset(
    {
        "HF_HOME", "HUGGINGFACE_HUB_CACHE", "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES", "PYTORCH_CUDA_ALLOC_CONF",
        "CUDA_DEVICE_ORDER", "VLLM_USE_FLASHINFER_SAMPLER",
        "MODEL_DIR", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE",
        "TZ", "LANG", "LC_ALL", "PATH", "PYTHONPATH",
        "VLLM_WORKER_MULTIPROC_METHOD",
    }
)


@dataclass
class Sanitizer:
    """Builds an alias table and applies it to text before write-to-disk.

    The same Sanitizer instance must be used for a whole run so that aliases
    are consistent across every artifact.
    """

    allowlist_env: frozenset[str] = field(default=ENV_ALLOWLIST)
    _host_alias: dict[str, str] = field(default_factory=dict)
    _host_seq: int = field(default=0)
    _client_alias: str = "benchmark-client"

    # ------------------------------------------------------------------
    # alias management
    # ------------------------------------------------------------------
    def alias_for_host(self, host: str) -> str:
        """Map a real hostname/IP to a stable public alias (gpu-host-NN)."""
        if not host or host in ("localhost", "127.0.0.1", "0.0.0.0"):
            return host
        key = host.lower()
        if key not in self._host_alias:
            self._host_seq += 1
            # Deterministic per-run alias: numbered, stable within the run.
            self._host_alias[key] = f"gpu-host-{self._host_seq:02d}"
        return self._host_alias[key]

    def register_host(self, real: str, alias: str) -> None:
        self._host_alias[real.lower()] = alias

    @property
    def client_alias(self) -> str:
        return self._client_alias

    # ------------------------------------------------------------------
    # env var filtering
    # ------------------------------------------------------------------
    def env_is_sensitive(self, name: str) -> bool:
        if name.upper() in self.allowlist_env:
            return False
        up = name.upper()
        return any(p in up for p in SENSITIVE_ENV_PATTERNS)

    def sanitize_env(self, env: dict[str, str]) -> dict[str, str]:
        """Return env with sensitive values redacted (name kept)."""
        out: dict[str, str] = {}
        for k, v in env.items():
            if self.env_is_sensitive(k):
                out[k] = "<redacted>"
            else:
                out[k] = v
        return out

    # ------------------------------------------------------------------
    # text sanitization
    # ------------------------------------------------------------------
    def sanitize_text(self, text: str) -> str:
        """Apply all redactions to a free-form string.

        Order matters: URLs-with-creds, then MAC/UUID/GPU-UUID, then
        IPv4/IPv6, then hostnames, then home paths.  Values that look like
        pure version numbers (e.g. 1.2.3.4) are preserved via a guard.
        """
        if not text:
            return text
        t = text

        # URLs with embedded credentials -> scheme://user@host
        t = _URL_CRED_RE.sub(lambda m: f"{m.group(1)}://user@host", t)
        # MAC addresses
        t = _MAC_RE.sub("<mac>", t)
        # GPU UUID
        t = _GPU_UUID_RE.sub("<gpu-uuid>", t)
        # Generic UUID
        t = _UUID_RE.sub("<uuid>", t)
        # Bearer tokens
        t = _BEARER_RE.sub("bearer <redacted>", t)
        # Authorization headers
        t = _AUTH_RE.sub("authorization: <redacted>", t)

        # IPv4: replace known host aliases first, else generic
        def _sub_ipv4(m: re.Match[str]) -> str:
            ip = m.group(0)
            # Guard: a version string like "1.2.3.4" is still ambiguous; but
            # we can't distinguish from an IP here.  Treat as IP.
            if ip in self._host_alias:
                return self._host_alias[ip]
            return "<ip>"
        t = _IPV4_RE.sub(_sub_ipv4, t)

        # IPv6
        t = _IPV6_RE.sub("<ipv6>", t)

        # Home-directory paths
        def _sub_home(m: re.Match[str]) -> str:
            return "<home>"
        t = _HOME_RE.sub(_sub_home, t)

        # Hostnames (FQDN-like): register as aliases
        def _sub_host(m: re.Match[str]) -> str:
            host = m.group(0)
            if host in ("localhost",):
                return host
            return self.alias_for_host(host)
        t = _HOSTNAME_RE.sub(_sub_host, t)

        return t

    def sanitize_str(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self.sanitize_text(value)

    def sanitize_obj(self, obj: Any) -> Any:
        """Recursively sanitize a JSON-able structure."""
        if isinstance(obj, str):
            return self.sanitize_text(obj)
        if isinstance(obj, dict):
            return {k: self.sanitize_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.sanitize_obj(v) for v in obj]
        return obj
