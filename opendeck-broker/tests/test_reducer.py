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


def test_dead_wins_over_untrusted():
    # derive_display precedence (research section 6): a dead instance (no live UI
    # attachment) is BLACK even if its telemetry is also untrusted -- the live
    # check comes before the trust check, so we never show an amber "?" for a
    # slot that has no occupant.
    assert derive_display(make(live=False, trusted=False)) is DisplayAppearance.BLACK


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


def test_retry_with_pending_input_is_input():
    # a retrying (RUN) session that also has an unresolved request shows INPUT,
    # not green (research section 6 precedence: INPUT > RUN)
    assert derive_display(make(status=Status.RETRY, questions=["q1"])) is DisplayAppearance.INPUT
    assert derive_display(make(status=Status.RETRY, perms=["p1"])) is DisplayAppearance.INPUT


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


def test_is_busy_reflects_status():
    # is_busy is True for BUSY and RETRY (both "executing"), False for IDLE.
    assert make(status=Status.BUSY).is_busy() is True
    assert make(status=Status.RETRY).is_busy() is True
    assert make(status=Status.IDLE).is_busy() is False


def test_add_ignores_empty_and_remove_unknown_is_noop():
    # add_* guards against a falsy request id (no empty-string entry); remove_*
    # with an unknown id is a clean no-op (no KeyError / no crash).
    inst = make(status=Status.IDLE)
    inst.add_permission("")
    inst.add_question("")
    assert inst.pending_permission_ids == []
    assert inst.pending_question_ids == []
    inst.add_permission("p1")
    inst.remove_permission("missing")  # unknown id, must not raise
    assert inst.pending_permission_ids == ["p1"]
    inst.remove_question("missing")  # unknown id, must not raise
    assert inst.pending_question_ids == []


def test_add_dedupes_and_remove_clears():
    # add_permission / add_question must not double-count the same request id,
    # and remove_* must clear it so INPUT resolves back to IDLE.
    inst = make(status=Status.IDLE)
    inst.add_permission("p1")
    inst.add_permission("p1")  # duplicate must not stack
    assert inst.pending_permission_ids == ["p1"]
    inst.add_question("q1")
    inst.add_question("q1")  # duplicate must not stack
    assert inst.pending_question_ids == ["q1"]
    assert inst.has_pending_input() is True
    inst.remove_permission("p1")
    inst.remove_question("q1")
    assert inst.has_pending_input() is False
    assert derive_display(inst) is DisplayAppearance.IDLE
