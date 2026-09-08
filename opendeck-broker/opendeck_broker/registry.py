"""Six-slot registry: immutable identity, generations, epoch/sequence ordering.

This is the heart of the broker. It owns the row-major six-slot assignment and
enforces the invariants the research calls out:

  * one button per live TUI instance;
  * keep an instance in the same slot until it closes (no compaction);
  * a seventh instance runs but gets no button (overflow), and never evicts a
    live occupant;
  * slot reuse increments a generation so a delayed press for the previous
    occupant cannot focus the new one;
  * per-producer-epoch monotonic sequences reject stale updates;
  * a broker restart changes the broker epoch, forcing clients to re-register.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from .model import DisplayAppearance, Instance, Process, derive_display

SLOT_COUNT = 6


@dataclass
class SlotState:
    slot: int
    instance_id: Optional[str]
    generation: int
    appearance: DisplayAppearance
    label: str = ""


@dataclass
class Registry:
    slots: int = SLOT_COUNT
    broker_epoch: str = field(default_factory=lambda: uuid.uuid4().hex)

    # slot index -> instance_id (or None if free)
    _slot_occupant: list = field(default_factory=lambda: [None] * SLOT_COUNT)
    # slot index -> generation counter
    _slot_generation: list = field(default_factory=list)
    # instance_id -> Instance
    _instances: dict = field(default_factory=dict)
    # instance_id -> slot index (or None if overflow)
    _instance_slot: dict = field(default_factory=dict)
    # instance_id -> (producer_epoch, sequence) last accepted
    _producer: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self._slot_generation) != self.slots:
            self._slot_generation = [0] * self.slots

    # ---------------- helpers ----------------
    @property
    def instances(self) -> dict:
        return self._instances

    def overflow(self) -> list[str]:
        """Live instances with no slot (a seventh, eighth, ... launch)."""
        return [
            iid for iid, slot in self._instance_slot.items()
            if slot is None and self._instances[iid].live
        ]

    # ---------------- registration ----------------
    def register(self, inst: Instance) -> Optional[int]:
        """Idempotently establish a live attachment and return the slot index.

        Reuse the existing assignment only for the same live instance identity
        (same instanceId). Otherwise allocate the lowest free slot. Never evict
        another live instance: if none are free the new instance is overflow
        (returns None).
        """
        inst.live = True
        self._instances[inst.instance_id] = inst
        self._producer[inst.instance_id] = (inst.producer_epoch, inst.sequence)

        existing = self._instance_slot.get(inst.instance_id)
        if existing is not None and self._slot_occupant[existing] == inst.instance_id:
            return existing  # idempotent re-register of the same live instance

        # find lowest free slot
        for i in range(self.slots):
            if self._slot_occupant[i] is None:
                self._slot_occupant[i] = inst.instance_id
                self._slot_generation[i] += 1  # slot reuse increments generation
                self._instance_slot[inst.instance_id] = i
                return i

        # all slots busy -> overflow (no button, still tracked)
        self._instance_slot[inst.instance_id] = None
        return None

    def _slot_of(self, instance_id: str) -> Optional[int]:
        return self._instance_slot.get(instance_id)

    # ---------------- snapshots (stale rejection) ----------------
    def accept_snapshot(
        self,
        inst: Instance,
        producer_epoch: Optional[str] = None,
        sequence: Optional[int] = None,
    ) -> bool:
        """Replace normalized state if the producer sequence is newer.

        Returns True if the snapshot was applied, False if rejected as stale or
        a different-epoch message (which must be preceded by a re-register).
        """
        epoch = producer_epoch if producer_epoch is not None else inst.producer_epoch
        seq = sequence if sequence is not None else inst.sequence
        last = self._producer.get(inst.instance_id)
        if last is None:
            # not registered yet: treat as a register
            self.register(inst)
            self._producer[inst.instance_id] = (epoch, seq)
            self._instances[inst.instance_id] = inst
            return True

        last_epoch, last_seq = last
        if epoch != last_epoch:
            # Different producer epoch = the adapter restarted. Without a
            # re-register we cannot trust a delta; reject (client must re-register).
            return False
        if seq <= last_seq:
            return False  # stale or duplicate

        # apply
        self._instances[inst.instance_id] = inst
        self._producer[inst.instance_id] = (epoch, seq)
        return True

    # ---------------- presence ----------------
    def heartbeat(self, instance_id: str) -> Optional[str]:
        """Renew presence. Returns the broker epoch so the client can detect a
        broker restart (it must then re-register with a full snapshot)."""
        if instance_id not in self._instances:
            return None
        return self.broker_epoch

    # ---------------- detach / death ----------------
    def _free_slot(self, instance_id: str) -> None:
        slot = self._instance_slot.pop(instance_id, None)
        if slot is not None and self._slot_occupant[slot] == instance_id:
            self._slot_occupant[slot] = None
        self._instances.pop(instance_id, None)
        self._producer.pop(instance_id, None)

    def detach(self, instance_id: str) -> bool:
        """Best-effort explicit detach."""
        return bool(self._free_slot(instance_id))

    def process_exit(self, instance_id: str) -> bool:
        """Local process-exit observation clears the slot immediately,
        regardless of any saved conversation."""
        return bool(self._free_slot(instance_id))

    def mark_untrusted(self, instance_id: str, trusted: bool) -> None:
        if instance_id in self._instances:
            self._instances[instance_id].telemetry_trusted = trusted

    # ---------------- render ----------------
    def frame(self) -> list[SlotState]:
        """The desired six-slot frame, row-major order."""
        out: list[SlotState] = []
        for i in range(self.slots):
            iid = self._slot_occupant[i]
            inst = self._instances.get(iid)
            if inst is None or not inst.live:
                out.append(SlotState(i, None, self._slot_generation[i], DisplayAppearance.BLACK))
                continue
            out.append(
                SlotState(
                    slot=i,
                    instance_id=iid,
                    generation=self._slot_generation[i],
                    appearance=derive_display(inst),
                    label=inst.identity_label,
                )
            )
        return out

    def slot_generation(self, slot: int) -> int:
        return self._slot_generation[slot]

    def resolve(self, instance_id: str) -> Optional[SlotState]:
        """Resolve an instance to its current slot state (for a focus request)."""
        slot = self._instance_slot.get(instance_id)
        if slot is None:
            return None
        return self.frame()[slot]

    def validate_press(self, instance_id: str, expected_generation: Optional[int]) -> bool:
        """A delayed press for the previous generation must not focus the new
        occupant. If expected_generation is given and differs from the slot's
        current generation, the press is stale."""
        state = self.resolve(instance_id)
        if state is None:
            return False
        if expected_generation is not None and expected_generation != state.generation:
            return False
        return True

    def to_diagnostics(self) -> dict:
        return {
            "broker_epoch": self.broker_epoch,
            "slots": [
                {
                    "slot": s.slot,
                    "instance_id": s.instance_id,
                    "generation": s.generation,
                    "appearance": s.appearance.value,
                    "label": s.label,
                }
                for s in self.frame()
            ],
            "overflow": self.overflow(),
            "live_instances": [
                {
                    "instanceId": i.instance_id,
                    "pid": i.process.pid,
                    "status": i.status.value,
                    "pendingPermissionIds": list(i.pending_permission_ids),
                    "pendingQuestionIds": list(i.pending_question_ids),
                }
                for i in self._instances.values()
            ],
        }
