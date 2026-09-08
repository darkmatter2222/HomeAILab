import time

from opendeck_broker.model import Instance, Process, Status
from opendeck_broker.registry import Registry


def inst(iid, epoch="e1", seq=1, status=Status.IDLE, questions=()):
    return Instance(
        instance_id=iid,
        process=Process(pid=100 + len(iid)),
        ui_attachment_id=iid,
        directory=f"/d/{iid}",
        producer_epoch=epoch,
        sequence=seq,
        status=status,
        pending_question_ids=list(questions),
        identity_label=iid,
    )


def test_row_major_assignment_lowest_free_first():
    r = Registry()
    assert r.register(inst("a")) == 0
    assert r.register(inst("b")) == 1
    assert r.register(inst("c")) == 2
    # top row full, next is bottom-left (slot 3)
    assert r.register(inst("d")) == 3


def test_mark_untrusted_flips_appearance_to_unknown():
    # research section 6: untrustworthy/disconnected telemetry -> UNKNOWN (not a
    # lying green/amber). mark_untrusted is the single-writer's way to set it.
    from opendeck_broker.model import DisplayAppearance, derive_display

    r = Registry()
    r.register(inst("a", status=Status.BUSY))  # would be RUN while trusted
    a = r.instances["a"]
    assert derive_display(a) is DisplayAppearance.RUN
    r.mark_untrusted("a", False)  # bridge unavailable
    assert derive_display(a) is DisplayAppearance.UNKNOWN
    r.mark_untrusted("a", True)   # bridge back
    assert derive_display(a) is DisplayAppearance.RUN
    # an unknown instance id is a no-op (no crash)
    r.mark_untrusted("nope", False)


def test_no_compaction_when_one_closes():
    r = Registry()
    r.register(inst("a"))  # 0
    r.register(inst("b"))  # 1
    r.register(inst("c"))  # 2
    r.process_exit("b")    # frees slot 1
    # a and c keep their slots; a new instance takes the freed slot 1
    assert r.register(inst("d")) == 1
    frame = r.frame()
    assert frame[0].instance_id == "a"
    assert frame[2].instance_id == "c"


def test_seventh_instance_is_overflow_never_evicts():
    r = Registry()
    for n in "abcdef":
        r.register(inst(n))
    assert r.register(inst("g")) is None  # no slot
    assert r.overflow() == ["g"]
    # all six originals still present
    assert {s.instance_id for s in r.frame() if s.instance_id} == set("abcdef")


def test_idempotent_reregister_same_instance():
    r = Registry()
    assert r.register(inst("a", seq=1)) == 0
    assert r.register(inst("a", seq=2)) == 0  # same live instance, same slot


def test_slot_reuse_increments_generation():
    r = Registry()
    r.register(inst("a"))          # slot 0, gen 1
    r.process_exit("a")            # frees slot 0
    r.register(inst("b"))          # slot 0, gen 2
    assert r.slot_generation(0) == 2


def test_stale_sequence_rejected():
    r = Registry()
    r.register(inst("a", seq=5))
    assert r.accept_snapshot(inst("a", seq=4), "e1", 4) is False  # older seq
    assert r.accept_snapshot(inst("a", seq=5), "e1", 5) is False  # duplicate
    assert r.accept_snapshot(inst("a", seq=6), "e1", 6) is True


def test_different_epoch_rejected_without_reregister():
    r = Registry()
    r.register(inst("a", epoch="e1", seq=1))
    # adapter restarted -> new epoch; a delta with a new epoch is rejected
    assert r.accept_snapshot(inst("a", epoch="e2", seq=99), "e2", 99) is False
    # but a re-register under the new epoch is accepted
    r.register(inst("a", epoch="e2", seq=100))
    assert r.accept_snapshot(inst("a", epoch="e2", seq=101), "e2", 101) is True


def test_accept_snapshot_not_registered_yet_registers():
    # a snapshot for an instance that has not been registered yet is treated as
    # a register (the first message a producer sends may be a snapshot, not a
    # register). The instance becomes live and a later register is idempotent.
    r = Registry()
    assert "a" not in r.instances
    assert r.accept_snapshot(inst("a", seq=1), "e1", 1) is True
    assert "a" in r.instances  # now registered
    assert r.frame()[0].instance_id == "a"  # got a slot
    assert r.register(inst("a", seq=1)) == 0  # a later register is idempotent


def test_stale_press_does_not_focus_new_occupant():
    r = Registry()
    r.register(inst("a"))  # slot 0 gen 1
    stale_gen = r.slot_generation(0)
    r.process_exit("a")
    r.register(inst("b"))  # slot 0 gen 2
    assert r.validate_press("a", stale_gen) is False
    assert r.validate_press("b", r.slot_generation(0)) is True


def test_process_exit_clears_slot_to_black():
    from opendeck_broker.model import DisplayAppearance

    r = Registry()
    r.register(inst("a"))
    r.process_exit("a")
    assert r.frame()[0].appearance is DisplayAppearance.BLACK
    assert r.frame()[0].instance_id is None


def test_frame_dead_occupant_renders_black():
    # a slot whose occupant is still in the registry but dead (live=False, not
    # yet freed) renders BLACK -- the frame checks `live` before rendering the
    # occupant's appearance, so a dying TUI reads black immediately.
    from opendeck_broker.model import DisplayAppearance

    r = Registry()
    busy = inst("a", status=Status.BUSY)
    slot = r.register(busy)
    assert r.frame()[slot].appearance is DisplayAppearance.RUN  # live -> RUN
    busy.live = False  # the process died but the slot is not yet freed
    assert r.frame()[slot].appearance is DisplayAppearance.BLACK
    assert r.frame()[slot].instance_id is None  # reported as unoccupied


def test_broker_epoch_changes_between_registries():
    a, b = Registry(), Registry()
    assert a.broker_epoch != b.broker_epoch


def test_heartbeat_returns_broker_epoch():
    r = Registry()
    r.register(inst("a"))
    assert r.heartbeat("a") == r.broker_epoch
    assert r.heartbeat("nope") is None


def test_lease_sweep_frees_a_quiet_producer():
    # research section 14: fallback cleanup within the configured lease window
    r = Registry()
    r.register(inst("a"))
    now = time.monotonic()
    # a generous lease keeps the just-registered instance
    assert r.sweep_expired(lease_seconds=60, now=now) == []
    assert "a" in r.instances
    # simulate 100 s passing with no further snapshot/heartbeat
    freed = r.sweep_expired(lease_seconds=10, now=now + 100)
    assert freed == ["a"]
    assert "a" not in r.instances


def test_lease_sweep_heartbeat_keeps_instance_alive():
    r = Registry()
    r.register(inst("a"))
    now = time.monotonic()
    # a heartbeat just before the sweep refreshes last_seen
    r.heartbeat("a")
    assert r.sweep_expired(lease_seconds=10, now=time.monotonic()) == []
    assert "a" in r.instances


def test_lease_sweep_frees_multiple_quiet_producers():
    # several quiet instances past the lease are all freed in one sweep (the
    # fallback cleanup is not limited to a single stale producer).
    r = Registry()
    r.register(inst("a"))
    r.register(inst("b"))
    r.register(inst("c"))
    now = time.monotonic()
    freed = r.sweep_expired(lease_seconds=10, now=now + 100)
    assert set(freed) == {"a", "b", "c"}
    assert r.instances == {}


def test_validate_press_unknown_instance_is_false():
    # a press for an instance that is no longer in the registry is a clean no-op
    # (False), not a crash -- a stale key press after its TUI left.
    r = Registry()
    r.register(inst("a"))
    assert r.validate_press("missing", 1) is False
    # the live instance still validates
    assert r.validate_press("a", r.slot_generation(0)) is True


def test_to_diagnostics_reports_slots_overflow_and_live():
    # the diagnostics payload (surfaced by /v1/diagnostics) must reflect the six
    # slots, the overflow set, and every live instance's status.
    r = Registry()
    r.register(inst("a"))
    r.register(inst("b", status=Status.BUSY))
    for i in range(2, 6):  # fill the remaining slots so the next one overflows
        r.register(inst(f"x{i}"))
    r.register(inst("overflow7"))
    diag = r.to_diagnostics()
    assert diag["broker_epoch"] == r.broker_epoch
    assert len(diag["slots"]) == 6
    assert diag["slots"][0]["instance_id"] == "a"
    assert diag["slots"][1]["instance_id"] == "b"
    assert diag["overflow"] == ["overflow7"]
    ids = {i["instanceId"] for i in diag["live_instances"]}
    assert ids == {"a", "b", "x2", "x3", "x4", "x5", "overflow7"}
    b = next(i for i in diag["live_instances"] if i["instanceId"] == "b")
    assert b["status"] == "busy"


def test_resolve_maps_instance_to_current_slot_state():
    # resolve maps a live instance to its current SlotState (a focus target);
    # an unknown instance resolves to None.
    from opendeck_broker.model import DisplayAppearance

    r = Registry()
    r.register(inst("a", status=Status.IDLE))
    state = r.resolve("a")
    assert state is not None
    assert state.instance_id == "a"
    assert state.appearance is DisplayAppearance.IDLE
    assert r.resolve("missing") is None
