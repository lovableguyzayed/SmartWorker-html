"""Limits on the three ways in: OTP request, OTP check and password.

Before this, the one-time code sat in Flask's session cookie in plain sight.
That cookie is signed, not encrypted, so anyone could ask for a code for
somebody else's number, base64-decode their own cookie, read the six digits
and sign in as that person. Nothing counted wrong codes or wrong passwords
either, and because the session lives in the cookie, any counter kept there
could be undone by replaying an older copy of it.

So the cookie now carries only a keyed hash of the code, and every counter
lives here on the server.

The counters are in process memory. With Render's two gunicorn workers an
attacker gets at most twice the allowance, and a restart clears them. That
is a limit, not a wall; a table in the database would make it exact, and is
listed in the audit as a decision because it is a schema change.
"""
import hashlib
import hmac
import re
import threading
import time

from flask import current_app, request

OTP_TTL_SECONDS = 300          # a code is good for five minutes
OTP_RESEND_SECONDS = 30        # and a new one can be asked for after thirty

# (how many, within how many seconds)
LIMITS = {
    'otp_send_mobile': (3, 15 * 60),     # codes sent to one number
    'otp_send_ip': (10, 60 * 60),        # codes asked for from one address
    'otp_fail_mobile': (5, 15 * 60),     # wrong codes for one number
    'otp_fail_ip': (20, 60 * 60),        # wrong codes from one address
    'pw_fail_id': (8, 15 * 60),          # wrong passwords for one login
    'pw_fail_ip': (30, 15 * 60),         # wrong passwords from one address
}

_lock = threading.Lock()
_hits = {}        # (bucket, key) -> [timestamps]
_used = {}        # nonce -> expiry; a code that already signed someone in


def _now():
    return time.time()


def _prune(stamps, window, now):
    cutoff = now - window
    while stamps and stamps[0] <= cutoff:
        stamps.pop(0)


def blocked_for(bucket, key):
    """Seconds until `key` may try again in `bucket`; 0 if it may now."""
    if not key:
        return 0
    limit, window = LIMITS[bucket]
    now = _now()
    with _lock:
        stamps = _hits.get((bucket, key))
        if not stamps:
            return 0
        _prune(stamps, window, now)
        if len(stamps) < limit:
            return 0
        return max(1, int(stamps[0] + window - now))


def record(bucket, key):
    if not key:
        return
    limit, window = LIMITS[bucket]
    now = _now()
    with _lock:
        stamps = _hits.setdefault((bucket, key), [])
        _prune(stamps, window, now)
        stamps.append(now)


def remaining(bucket, key):
    """How many more tries `key` has in `bucket` before it must wait."""
    limit, window = LIMITS[bucket]
    now = _now()
    with _lock:
        stamps = _hits.get((bucket, key), [])
        _prune(stamps, window, now)
        return max(0, limit - len(stamps))


def clear(bucket, key):
    with _lock:
        _hits.pop((bucket, key), None)


def client_ip():
    # ProxyFix in app.py has already put the real address here on Render.
    return request.remote_addr or 'unknown'


def minutes(seconds):
    """A wait in whole minutes, rounded up, never zero."""
    return max(1, (seconds + 59) // 60)


# ---- the code itself -------------------------------------------------------

def otp_digest(purpose, mobile, code, nonce):
    """What the session holds instead of the code: a hash keyed with the
    app's secret, so knowing the cookie tells you nothing about the code."""
    key = (current_app.secret_key or '').encode() if isinstance(current_app.secret_key, str) \
        else (current_app.secret_key or b'')
    msg = '|'.join((purpose, mobile, str(code), nonce)).encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def otp_matches(purpose, mobile, code, nonce, digest):
    if not (digest and nonce and code):
        return False
    return hmac.compare_digest(otp_digest(purpose, mobile, code, nonce), digest)


def mark_used(nonce):
    """A code that worked once must not work again from a replayed cookie."""
    now = _now()
    with _lock:
        for n in [n for n, exp in _used.items() if exp < now]:
            _used.pop(n, None)
        _used[nonce] = now + OTP_TTL_SECONDS


def was_used(nonce):
    with _lock:
        exp = _used.get(nonce)
        return bool(exp and exp >= _now())


# ---- Indian mobile numbers -------------------------------------------------

_INDIAN_MOBILE = re.compile(r'^[6-9]\d{9}$')


def indian_mobile(value):
    """The ten digits of an Indian mobile number, however it was typed or
    pasted: '+91 98765-43210', '09876543210', '919876543210' and
    '98765 43210' are all '9876543210'. Anything that is not a valid Indian
    mobile comes back as ''."""
    digits = ''.join(ch for ch in (value or '') if ch.isdigit())
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    return digits if _INDIAN_MOBILE.match(digits) else ''


def stored_forms(mobile):
    """Every way an older row may have stored the same number. Numbers used
    to be kept as whatever digits were typed, so one person can sit in the
    table as 9876543210, 919876543210 or 09876543210."""
    if not mobile:
        return []
    return [mobile, '91' + mobile, '0' + mobile]


def reset_for_tests():
    with _lock:
        _hits.clear()
        _used.clear()
