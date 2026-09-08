"""Core data model + the display reducer.

The reducer is the single source of truth for what a slot shows. It is pure
and deterministic so it can be unit-tested against fixtures (see tests/).

State facts are kept separate (status vs pending permissions vs pending
questions) exactly as the research requires: an `idle` event must not clear an
outstanding request, and a child completing must not turn a waiting/running
parent amber.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Status(str, Enum):
    """OpenCode session status schema: idle / busy / retry."""

    IDLE = "idle"
    BUSY = "busy"
    RETRY = "retry"


class DisplayAppearance(str, Enum):
    """The four normal appearances + the degraded UNKNOWN.

    BLACK  : no live TUI assigned to this slot (solid black, no text).
    IDLE   : live instance, ready for another prompt (amber, "IDLE").
    RUN    : live instance executing/generating/prefilling/tool/retry (green, "RUN").
    INPUT  : unresolved permission or structured question (red, "INPUT").
    UNKNOWN: telemetry not trustworthy / transport disconnected (amber with "?").
    """

    BLACK = "black"
    IDLE = "idle"
    RUN = "run"
    INPUT = "input"
    UNKNOWN = "unknown"


# Reuse the RAG palette proven on the physical deck in the prior work.
APPEARANCE_COLOR: dict[DisplayAppearance, str] = {
    DisplayAppearance.RUN: "#2fd06f",
    DisplayAppearance.IDLE: "#f5b13d",
    DisplayAppearance.INPUT: "#ff5a4e",
    DisplayAppearance.UNKNOWN: "#f5b13d",  # amber, but labelled with "?"
    DisplayAppearance.BLACK: "#000000",
}

APPEARANCE_LABEL: dict[DisplayAppearance, str] = {
    DisplayAppearance.RUN: "RUN",
    DisplayAppearance.IDLE: "IDLE",
    DisplayAppearance.INPUT: "INPUT",
    DisplayAppearance.UNKNOWN: "?",
    DisplayAppearance.BLACK: "",
}


@dataclass(frozen=True)
class Process:
    """Process identity. PID alone is not enough: pair with creation time so a
    reused OS PID does not look like the same live instance."""

    pid: int
    start_time: Optional[int] = None  # verified process creation time (epoch ms)

    def matches(self, other: "Process") -> bool:
        if self.pid != other.pid:
            return False
        # If both carry a start time, they must agree; otherwise fall back to
        # pid equality (creation time unavailable).
        if self.start_time is not None and other.start_time is not None:
            return self.start_time == other.start_time
        return True


@dataclass
class Instance:
    """A live OpenCode TUI launch. Immutable identity, mutable state facts.

    `instanceId` is a fresh UUID per launch. The broker validates process/window
    metadata locally; it does not blindly trust a submitted PID.
    """

    instance_id: str
    process: Process
    ui_attachment_id: str
    directory: str
    focus_target: Optional[dict] = None  # {kind, opaqueId} validated by the host

    # --- per-producer sequencing (stale-message rejection) ---
    producer_epoch: str = ""
    sequence: int = 0

    # --- state facts (kept separate on purpose) ---
    status: Status = Status.IDLE
    pending_permission_ids: list[str] = field(default_factory=list)
    pending_question_ids: list[str] = field(default_factory=list)
    error: Optional[str] = None

    # --- broker-side bookkeeping (not part of the bridge payload) ---
    live: bool = True
    telemetry_trusted: bool = True
    identity_label: str = ""  # short identity rendered on the key

    # ---- state transitions (reducer inputs) ----
    def set_status(self, status: Status) -> None:
        # An idle/busy/retry transition must NOT erase outstanding requests.
        self.status = status

    def add_permission(self, request_id: str) -> None:
        if request_id and request_id not in self.pending_permission_ids:
            self.pending_permission_ids.append(request_id)

    def remove_permission(self, request_id: str) -> None:
        if request_id in self.pending_permission_ids:
            self.pending_permission_ids.remove(request_id)

    def add_question(self, request_id: str) -> None:
        if request_id and request_id not in self.pending_question_ids:
            self.pending_question_ids.append(request_id)

    def remove_question(self, request_id: str) -> None:
        if request_id in self.pending_question_ids:
            self.pending_question_ids.remove(request_id)

    def has_pending_input(self) -> bool:
        return bool(self.pending_permission_ids or self.pending_question_ids)

    def is_busy(self) -> bool:
        return self.status in (Status.BUSY, Status.RETRY)


def derive_display(inst: Optional[Instance]) -> DisplayAppearance:
    """Pure reducer: turn an instance's separate facts into one appearance.

    Precedence (per research section 6):
      1. no live UI attachment            -> BLACK
      2. telemetry not trustworthy         -> UNKNOWN
      3. any unresolved permission/question -> INPUT (red)
      4. any session busy or retrying      -> RUN (green)
      5. otherwise                         -> IDLE (amber)
    """
    if inst is None or not inst.live:
        return DisplayAppearance.BLACK
    if not inst.telemetry_trusted:
        return DisplayAppearance.UNKNOWN
    if inst.has_pending_input():
        return DisplayAppearance.INPUT
    if inst.is_busy():
        return DisplayAppearance.RUN
    return DisplayAppearance.IDLE
