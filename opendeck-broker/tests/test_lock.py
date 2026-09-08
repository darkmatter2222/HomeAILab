from opendeck_broker.lock import BrokerLock


def test_single_instance_lock_excludes_second():
    a = BrokerLock()
    b = BrokerLock()
    assert a.acquire() is True
    # a second broker must be rejected while the first holds the lock
    assert b.acquire() is False
    a.release()
    # after release, the second can acquire
    assert b.acquire() is True
    b.release()


def test_release_is_idempotent_enough_to_reacquire():
    a = BrokerLock()
    assert a.acquire() is True
    a.release()
    c = BrokerLock()
    assert c.acquire() is True
    c.release()
