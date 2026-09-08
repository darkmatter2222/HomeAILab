"""OpenCode state observation from the shared global SQLite store.

Every OpenCode process (TUI and `opencode serve`) persists to the same global
DB. Reading it gives one source that covers every session type (research
section 5: the "known reachable" integration, verified on this machine in the
prior work). State facts are kept separate:

  * status  -> idle / busy / retry (last-part recency is a debounce, not a guess)
  * pending question parts   -> INPUT
  * pending permission parts -> INPUT

A completed answer ending in ordinary prose is still IDLE; only an unresolved
structured request is INPUT. This matches the prior, physically-verified state
machine in the Elgato plugin.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..model import Status

RUN_WINDOW_MS = 15_000

QUERY = """
SELECT s.id, s.directory, s.title,
  (SELECT MAX(p.time_updated) FROM part p WHERE p.session_id = s.id) AS last_part_upd,
  (SELECT COUNT(*) FROM part p WHERE p.session_id = s.id
     AND json_extract(p.data,'$.type')='tool'
     AND json_extract(p.data,'$.tool')='question'
     AND json_extract(p.data,'$.state.status') != 'completed'
   ) AS pending_q,
  (SELECT COUNT(*) FROM part p WHERE p.session_id = s.id
     AND json_extract(p.data,'$.type')='tool'
     AND json_extract(p.data,'$.tool')='permission'
     AND json_extract(p.data,'$.state.status') != 'completed'
    ) AS pending_perm,
  (SELECT COUNT(*) FROM part p WHERE p.session_id = s.id
     AND json_extract(p.data,'$.type')='tool'
     AND json_extract(p.data,'$.state.status') IN ('running','pending')
    ) AS active_tool
FROM session s
WHERE (s.time_archived IS NULL OR s.time_archived = 0);
"""


def default_db_path() -> Path:
    return Path(os.environ.get("OPENCODE_DB", "")) if os.environ.get("OPENCODE_DB") else (
        Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    )


@dataclass
class SessionState:
    """Aggregated state facts for one directory (one tracked TUI in the initial
    supported mode: one root conversation per launch)."""

    directory: str
    has_session: bool = False
    status: Status = Status.IDLE
    pending_questions: list[str] = field(default_factory=list)
    pending_permissions: list[str] = field(default_factory=list)
    session_id: str = ""
    title: str = ""

    @property
    def has_pending_input(self) -> bool:
        return bool(self.pending_questions or self.pending_permissions)


class DbObserver:
    def __init__(self, db_path: Optional[os.PathLike] = None, run_window_ms: int = RUN_WINDOW_MS) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.run_window_ms = run_window_ms

    def _now_ms(self) -> int:
        import time

        return int(time.time() * 1000)

    def snapshot_by_directory(self) -> dict[str, SessionState]:
        """Read the DB and aggregate per-directory state facts.

        For each directory we take the most recently updated live session and
        fold any pending requests from all of its live sessions (a child with a
        pending request contributes INPUT to the owning TUI without taking a
        separate slot).
        """
        if not self.db_path.exists():
            return {}
        now = self._now_ms()
        # Read-only URI so the observer never grabs a write lock on OpenCode's
        # live store (WAL lets a reader coexist with OpenCode's writer).
        conn = sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=2.0)
        try:
            rows = conn.execute(QUERY).fetchall()
        finally:
            conn.close()

        by_dir: dict[str, SessionState] = {}
        latest: dict[str, Optional[int]] = {}
        active_tool: dict[str, int] = {}
        for sid, directory, title, last_part_upd, pending_q, pending_perm, active in rows:
            d = _norm_dir(directory)
            st = by_dir.get(d)
            if st is None:
                st = SessionState(directory=d, session_id=sid, title=title or "")
                by_dir[d] = st
            # accumulate pending requests across all live sessions in this dir
            st.pending_questions.extend([f"q-{sid}-{i}" for i in range(int(pending_q or 0))])
            st.pending_permissions.extend([f"p-{sid}-{i}" for i in range(int(pending_perm or 0))])
            # track the most recent part update for the directory (busy/idle)
            if d not in latest or (last_part_upd or 0) > (latest[d] or 0):
                latest[d] = last_part_upd
            # a tool still executing keeps the TUI busy even without fresh parts
            active_tool[d] = max(active_tool.get(d, 0), int(active or 0))

        for d, st in by_dir.items():
            st.has_session = True
            lpu = latest.get(d)
            # Busy if a tool is still running/pending (a long tool without token
            # streaming) OR a part was updated within the window; otherwise idle.
            # The window is a debounce, not a state guess.
            tool_running = active_tool.get(d, 0) > 0
            recent = lpu is not None and now - lpu < self.run_window_ms
            st.status = Status.BUSY if (tool_running or recent) else Status.IDLE
        return by_dir


def _norm_dir(directory: Optional[str]) -> str:
    return str(directory or "").replace("\\", "/").rstrip("/")
