from app.core.cooldown import visit_status


def test_no_prior_visit_unlocked():
    assert visit_status(None, 1000.0) == (False, 0.0)


def test_within_cooldown_locked_with_remaining():
    locked, rem = visit_status(1000.0, 1000.0 + 120, cooldown_min=5)  # 2 min in
    assert locked is True and abs(rem - 180.0) < 1e-6


def test_after_cooldown_unlocked():
    locked, rem = visit_status(1000.0, 1000.0 + 301, cooldown_min=5)
    assert locked is False and rem == 0.0


def test_time_scale_shrinks_window():
    # 5-min gate at scale 10 → real window is 30 s; remaining is wall-seconds.
    locked, rem = visit_status(1000.0, 1000.0 + 20, cooldown_min=5, time_scale=10)
    assert locked is True and abs(rem - 10.0) < 1e-6  # 30s window − 20s elapsed
    assert visit_status(1000.0, 1000.0 + 31, cooldown_min=5, time_scale=10)[0] is False
