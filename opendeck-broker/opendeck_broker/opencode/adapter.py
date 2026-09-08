"""OpenCode adapter: bind TUI launches to the broker and push observed state.

One tracked root conversation per launch (the initial supported mode). The
adapter owns a fresh instanceId + producer epoch per launch, observes the global
DB, and pushes normalized state to the broker's registry with a monotonically
increasing sequence so stale messages are rejected.

A TUI at its home screen (no conversation yet) is IDLE: the observer finds no
session for the directory, so the instance stays amber -- matching the
"launch one TUI at its home screen -> exactly one amber key" acceptance test.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from ..model import Instance, Process, Status
from ..process import is_alive
from ..registry import Registry
from .observe import DbObserver, _norm_dir


@dataclass
class Launch:
    instance_id: str
    directory: str
    marker: str
    instance: Instance


class OpenCodeAdapter:
    def __init__(self, registry: Registry, observer: DbObserver) -> None:
        self.registry = registry
        self.observer = observer
        self.producer_epoch = uuid.uuid4().hex
        self._seq = 0
        self._launches: dict[str, Launch] = {}

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    # ------------------------------------------------------------------ #
    def register_launch(
        self,
        directory: str,
        alias: str,
        pid: int,
        start_time: Optional[int] = None,
        focus_target: Optional[dict] = None,
    ) -> tuple[str, Optional[int]]:
        instance_id = uuid.uuid4().hex
        # Unique launch token per TUI (research: "Launch token plus validated
        # window and terminal binding"). Two TUIs in the same directory share
        # an alias but must get distinct window identities, so the marker is
        # suffixed with a per-launch id. The on-key label stays the alias.
        if focus_target and focus_target.get("opaqueId"):
            marker = focus_target["opaqueId"]
        else:
            marker = f"opencode:{alias}-{instance_id[:6]}"
        instance = Instance(
            instance_id=instance_id,
            process=Process(pid=pid, start_time=start_time),
            ui_attachment_id=instance_id,
            directory=_norm_dir(directory),
            focus_target=focus_target or {"kind": "windows-terminal-window", "opaqueId": marker},
            producer_epoch=self.producer_epoch,
            sequence=self._next_seq(),
            identity_label=alias,
        )
        slot = self.registry.register(instance)
        self._launches[instance_id] = Launch(
            instance_id=instance_id, directory=_norm_dir(directory), marker=marker, instance=instance
        )
        return instance_id, slot

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """Re-read the global DB and push per-instance state to the registry."""
        try:
            states = self.observer.snapshot_by_directory()
            db_ok = True
        except Exception:
            states, db_ok = {}, False

        for launch in list(self._launches.values()):
            # Local process-exit observation clears the slot immediately,
            # regardless of any saved conversation (research sections 6, 7).
            proc = launch.instance.process
            if not is_alive(proc.pid, proc.start_time):
                self.mark_dead(launch.instance_id)
                continue
            inst = launch.instance
            st = states.get(_norm_dir(launch.directory))
            inst.telemetry_trusted = db_ok
            if st is None or not st.has_session:
                # TUI open, no conversation yet -> IDLE (amber), not UNKNOWN.
                inst.set_status(Status.IDLE)
                inst.pending_question_ids = []
                inst.pending_permission_ids = []
            else:
                inst.set_status(st.status)
                inst.pending_question_ids = list(st.pending_questions)
                inst.pending_permission_ids = list(st.pending_permissions)
            seq = self._next_seq()
            inst.sequence = seq
            self.registry.accept_snapshot(inst, self.producer_epoch, seq)

    def detach(self, instance_id: str) -> bool:
        self._launches.pop(instance_id, None)
        return self.registry.detach(instance_id)

    def mark_dead(self, instance_id: str) -> bool:
        self._launches.pop(instance_id, None)
        return self.registry.process_exit(instance_id)

    def heartbeat(self, instance_id: str) -> Optional[str]:
        return self.registry.heartbeat(instance_id)

    def launches(self) -> list[Launch]:
        return list(self._launches.values())
