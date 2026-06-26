from app.core.auth import pin_hash, make_token, read_token, RateLimiter


def test_token_roundtrip():
    tok = make_token("secret", "member", "0-1")
    assert read_token("secret", tok) == {"role": "member", "member_id": "0-1"}
    assert read_token("secret", "garbage") is None


def test_pin_hash_stable():
    assert pin_hash("1234") == pin_hash("1234") and len(pin_hash("1234")) == 64


def test_rate_limiter_blocks_after_max():
    rl = RateLimiter(max_per_min=3)
    assert all(rl.check("1.1.1.1") for _ in range(3))
    assert rl.check("1.1.1.1") is False
    assert rl.check("2.2.2.2") is True
