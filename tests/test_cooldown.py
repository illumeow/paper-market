from app.core.cooldown import visit_status


def test_no_prior_visit_unlocked():
    assert visit_status(None, 1000.0) == (False, 0.0)


def test_within_cooldown_locked_with_remaining():
    locked, rem = visit_status(1000.0, 1000.0 + 120, cooldown_min=5)  # 2 min in
    assert locked is True and abs(rem - 180.0) < 1e-6


def test_after_cooldown_unlocked():
    locked, rem = visit_status(1000.0, 1000.0 + 301, cooldown_min=5)
    assert locked is False and rem == 0.0
