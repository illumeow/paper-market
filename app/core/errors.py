class BusinessError(ValueError):
    """A domain rejection meant to be shown to the user (HTTP 400), not a server fault.

    Use this for expected, user-facing refusals: insufficient balance, invalid
    amount, relief already claimed, etc. A bare ``ValueError`` (or any other
    exception) stays an unhandled 500 — a *true* error worth investigating.

    Subclasses ``ValueError`` so existing ``pytest.raises(ValueError)`` still match.
    """
