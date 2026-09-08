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


def test_broker_epoch_changes_between_registries():
    a, b = Registry(), Registry()
    assert a.broker_epoch != b.broker_epoch


def test_heartbeat_returns_broker_epoch():
    r = Registry()
    r.register(inst("a"))
    assert r.heartbeat("a") == r.broker_epoch
    assert r.heartbeat("nope") is None
