import hashlib
import time
from collections import defaultdict, deque
from fastapi import Request, HTTPException
from itsdangerous import URLSafeSerializer, BadSignature

COOKIE = "pm_session"


def pin_hash(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def make_token(secret, role, member_id=None) -> str:
    return URLSafeSerializer(secret, salt="pm").dumps({"role": role, "member_id": member_id})


def read_token(secret, token):
    try:
        data = URLSafeSerializer(secret, salt="pm").loads(token)
    except (BadSignature, Exception):
        return None
    # normalize: drop member_id key when None? keep explicit for tests
    return {"role": data.get("role"), "member_id": data.get("member_id")}


def _session(request: Request):
    secret = request.app.state.config.secret_key
    tok = request.cookies.get(COOKIE)
    return read_token(secret, tok) if tok else None


def require_member(request: Request):
    s = _session(request)
    if not s or s["role"] != "member":
        raise HTTPException(401, "Login required")
    return s["member_id"]


def require_staff(request: Request):
    s = _session(request)
    if not s or s["role"] != "staff":
        raise HTTPException(403, "Staff only")
    return True


class RateLimiter:
    def __init__(self, max_per_min):
        self.max = max_per_min
        self.hits = defaultdict(deque)

    def check(self, ip) -> bool:
        now = time.time()
        dq = self.hits[ip]
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= self.max:
            return False
        dq.append(now)
        return True
