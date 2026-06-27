def visit_status(last_visit_epoch, now_epoch, cooldown_min=5, time_scale=1.0):
    """Teller-visit gate. ``remaining`` is real wall-clock seconds the member
    must wait. ``time_scale`` shrinks the window so TIME_SCALE testing compresses
    the cooldown like every other clock (scale=10 → 5-min gate clears in 30 s)."""
    if last_visit_epoch is None:
        return (False, 0.0)
    window = cooldown_min * 60 / time_scale
    remaining = window - (now_epoch - last_visit_epoch)
    if remaining > 0:
        return (True, remaining)
    return (False, 0.0)
