from opendeck_broker.model import (
    DisplayAppearance,
    Instance,
    Process,
    Status,
    derive_display,
)


def make(status=Status.IDLE, perms=(), questions=(), live=True, trusted=True):
    return Instance(
        instance_id="x",
        process=Process(pid=1),
        ui_attachment_id="x",
        directory="/d",
        status=status,
        pending_permission_ids=list(perms),
        pending_question_ids=list(questions),
        live=live,
        telemetry_trusted=trusted,
    )


def test_none_or_dead_is_black():
    assert derive_display(None) is DisplayAppearance.BLACK
    assert derive_display(make(live=False)) is DisplayAppearance.BLACK


def test_untrusted_is_unknown():
    assert derive_display(make(trusted=False)) is DisplayAppearance.UNKNOWN


def test_idle_is_amber():
    assert derive_display(make(status=Status.IDLE)) is DisplayAppearance.IDLE


def test_busy_is_run():
    assert derive_display(make(status=Status.BUSY)) is DisplayAppearance.RUN


def test_retry_is_run():
    # automatic retry is green (RUN), not a user prompt
    assert derive_display(make(status=Status.RETRY)) is DisplayAppearance.RUN


def test_pending_permission_is_input_even_if_idle():
    # an idle event must not clear an outstanding request
    assert derive_display(make(status=Status.IDLE, perms=["p1"])) is DisplayAppearance.INPUT


def test_pending_question_is_input_even_if_busy():
    # INPUT has precedence over RUN
    assert derive_display(make(status=Status.BUSY, questions=["q1"])) is DisplayAppearance.INPUT


def test_two_pending_resolving_one_stays_input():
    inst = make(status=Status.IDLE, perms=["p1", "p2"])
    assert derive_display(inst) is DisplayAppearance.INPUT
    inst.remove_permission("p1")
    assert derive_display(inst) is DisplayAppearance.INPUT
    inst.remove_permission("p2")
    assert derive_display(inst) is DisplayAppearance.IDLE


def test_child_complete_does_not_clear_parent_waiting():
    inst = make(status=Status.BUSY, questions=["q-parent"])
    # child completes -> status flips to idle, but the parent's question remains
    inst.set_status(Status.IDLE)
    assert derive_display(inst) is DisplayAppearance.INPUT


def test_idle_does_not_erase_outstanding_requests():
    inst = make(status=Status.BUSY, questions=["q1"])
    inst.set_status(Status.IDLE)  # idle event arrives
    assert derive_display(inst) is DisplayAppearance.INPUT
