def visit_status(last_visit_epoch, now_epoch, cooldown_min=5):
    if last_visit_epoch is None:
        return (False, 0.0)
    remaining = cooldown_min * 60 - (now_epoch - last_visit_epoch)
    if remaining > 0:
        return (True, remaining)
    return (False, 0.0)
