import hashlib

from django.core.cache import cache


MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def _cache_key(username, ip_address):
    """
    Build a cache key without storing the raw username or IP.
    """
    value = f"{username.strip().lower()}|{ip_address or 'unknown'}"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()

    return f"login_throttle:{digest}"


def is_locked_out(username, ip_address):
    """
    Return True after the maximum failed attempts are reached.
    """
    key = _cache_key(username, ip_address)
    attempts = cache.get(key, 0)

    return attempts >= MAX_FAILED_ATTEMPTS


def register_failed_login(username, ip_address):
    """
    Count a failed login attempt.
    The counter expires after 15 minutes.
    """
    key = _cache_key(username, ip_address)
    attempts = cache.get(key, 0)

    attempts += 1

    cache.set(
        key,
        attempts,
        timeout=LOCKOUT_SECONDS,
    )

    return attempts


def clear_failed_logins(username, ip_address):
    """
    Clear the failed login counter after successful authentication.
    """
    key = _cache_key(username, ip_address)
    cache.delete(key)