"""The broker: one process that owns the six slots.

It coordinates status and focus; it does not proxy model requests (research
section 4). Wires together:

  * the six-slot registry (identity, generations, stale rejection)
  * a single device adapter (option A: direct HID Mini)
  * a Windows focus adapter (presses only focus, never mutate state)
  * the image renderer (color + identity baked into one image per key)

Presses are captured on the device reader thread and processed on the broker
loop, so foreground/network work never runs in the reader thread (research
section 11).
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from .device.base import DeviceAdapter
from .focus.windows import FocusResult, FocusStatus, WindowsFocusAdapter
from .images import DEFAULT_KEY_SIZE, render_key
from .model import DisplayAppearance
from .registry import Registry


class Broker:
    def __init__(
        self,
        registry: Optional[Registry] = None,
        device: Optional[DeviceAdapter] = None,
        focus: Optional[WindowsFocusAdapter] = None,
        image_size: int = DEFAULT_KEY_SIZE,
    ) -> None:
        self.registry = registry or Registry()
        self.device = device
        self.focus = focus
        self.image_size = image_size
        # (slot, captured_instance_id, captured_generation) pending press edges
        self._press_queue: deque = deque()
        # diagnostics: last focus attempts
        self.focus_log: list[dict] = []
        self._started = False

    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        """Connect the device and upload an initial six-black frame.

        We explicitly upload black (research section 8): do not assume a
        `reset` clears to black, and do not restore any old assignment.
        """
        if self.device is not None and not self.device.is_connected():
            if not self.device.connect():
                return False
        if self.device is not None:
            # Press edges are captured here (reader thread) and processed on the
            # broker loop via process_presses().
            self.device.set_key_press_handler(self.on_key)
        self.upload_black_frame()
        self._started = True
        return True

    def stop(self) -> None:
        """Graceful shutdown: black out the keys when possible."""
        try:
            self.upload_black_frame()
        finally:
            if self.device is not None:
                self.device.close()
            self._started = False

    # ------------------------------------------------------------------ #
    def upload_black_frame(self) -> None:
        if self.device is None:
            return
        black = render_key(DisplayAppearance.BLACK, size=self.image_size)
        for i in range(self.registry.slots):
            self.device.set_key_image(i, black)

    # ------------------------------------------------------------------ #
    def render(self) -> None:
        """Push the desired six-slot frame to the device, serialized per key and
        cached so identical images are not re-uploaded (USB traffic)."""
        if self.device is None:
            return
        for ss in self.registry.frame():
            image = render_key(ss.appearance, ss.label, size=self.image_size)
            self.device.set_key_image(ss.slot, image)

    # ------------------------------------------------------------------ #
    def on_key(self, slot: int) -> None:
        """Device reader thread: capture the current occupant + generation and
        enqueue. No network/foreground work here."""
        ss = self.registry.frame()[slot]
        self._press_queue.append((slot, ss.instance_id, ss.generation))

    def pending_presses(self) -> int:
        return len(self._press_queue)

    def process_presses(self) -> list[dict]:
        """Broker loop: resolve + focus each captured press edge exactly once."""
        results = []
        while self._press_queue:
            slot, inst_id, gen = self._press_queue.popleft()
            results.append(self._handle_press(slot, inst_id, gen))
        return results

    def _handle_press(self, slot: int, inst_id: Optional[str], gen: int) -> dict:
        entry = {"slot": slot, "instance_id": inst_id, "expected_generation": gen}
        if inst_id is None:
            # Black key: no window, process, command, or state change.
            entry["result"] = "no_occupant"
            self.focus_log.append(entry)
            return entry

        # Stale-press guard: if the slot's occupant/generation changed since the
        # edge was captured, this is a delayed press for the previous occupant.
        if not self.registry.validate_press(inst_id, gen):
            entry["result"] = "stale"
            self.focus_log.append(entry)
            return entry

        inst = self.registry.instances.get(inst_id)
        marker = None
        if inst is not None and inst.focus_target:
            marker = inst.focus_target.get("opaqueId")
        if self.focus is None or marker is None:
            entry["result"] = "no_focus_target"
            self.focus_log.append(entry)
            return entry

        res: FocusResult = self.focus.focus_marker(marker)
        entry["result"] = res.status.value
        entry["hwnd"] = res.hwnd
        entry["observed_foreground"] = res.observed_foreground
        self.focus_log.append(entry)
        return entry

    # ------------------------------------------------------------------ #
    def focus_instance(self, instance_id: str, expected_generation: Optional[int] = None) -> FocusResult:
        """Programmatic focus (POST /v1/focus). Resolves the assignment and
        focuses; returns STALE if the generation no longer matches."""
        state = self.registry.resolve(instance_id)
        if state is None or not self.registry.validate_press(instance_id, expected_generation):
            return FocusResult(FocusStatus.STALE, detail=f"no live assignment for {instance_id}")
        inst = self.registry.instances[instance_id]
        marker = inst.focus_target.get("opaqueId") if inst.focus_target else None
        if not marker:
            return FocusResult(FocusStatus.NOT_FOUND, detail="no focus target")
        return self.focus.focus_marker(marker)

    def diagnostics(self) -> dict:
        return {
            "registry": self.registry.to_diagnostics(),
            "focus_log_tail": self.focus_log[-10:],
            "pending_presses": self.pending_presses(),
            "device_connected": bool(self.device and self.device.is_connected()),
        }
