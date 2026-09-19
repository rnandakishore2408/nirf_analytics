"""Sign-in for staff. There is no sign-up: accounts are created by the administrator with
scripts/manage_users.py and handed out.

  * Passwords are stored as scrypt hashes (salted, memory-hard); plain text is never stored or logged.
  * Five wrong passwords for a username within 15 minutes lock that username for 15 minutes. The rule
    is counted from login_events, so an unknown username behaves exactly like a real one and the form
    never reveals which usernames exist.
  * A session ends after 60 idle minutes or 12 hours, and is re-checked against the database every
    5 minutes, so disabling an account takes effect without a restart.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque

import live_store as store

SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2 ** 15, 8, 1, 32
SCRYPT_MAXMEM = 64 * 1024 * 1024
MAX_FAILS, LOCK_WINDOW_S = 5, 15 * 60
IDLE_TIMEOUT_S, ABSOLUTE_TIMEOUT_S, RECHECK_S = 60 * 60, 12 * 60 * 60, 5 * 60
MIN_PASSWORD_LEN = 10
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
GENERIC_FAIL = "Incorrect username or password."
LOCKED_MSG = "Too many attempts for this username. Please wait 15 minutes and try again."
COMMON = {"password", "password1", "password123", "1234567890", "qwerty123", "saveetha123", "admin12345", "letmein123",
          "welcome123", "nirf123456", "iloveyou12", "abcdefghij", "qwertyuiop", "0123456789", "changeme123"}


# ---------- hashing ----------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN, maxmem=SCRYPT_MAXMEM)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(dk)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(want), maxmem=SCRYPT_MAXMEM)
        return hmac.compare_digest(got, want)
    except Exception:  # noqa: BLE001 - a malformed hash is simply a failed check
        return False


# spent on unknown usernames so both paths take the same time
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def password_problems(password: str, username: str = "") -> list[str]:
    out = []
    if len(password) < MIN_PASSWORD_LEN:
        out.append(f"Use at least {MIN_PASSWORD_LEN} characters.")
    if len(password) > 128:
        out.append("Use at most 128 characters.")
    if username and username.lower() in password.lower():
        out.append("Do not include the username.")
    if password.lower() in COMMON:
        out.append("That password is too common.")
    if len(set(password)) < 5:
        out.append("Use a less repetitive password.")
    return out


def generate_password() -> str:
    """Readable random password, e.g. 'Kp7m-Qx2r-T9vb-3Hnw' (about 95 bits)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


def normalise(username: str) -> str:
    return (username or "").strip().lower()[:64]


# ---------- accounts ----------
def get_user(username: str) -> dict | None:
    rows = store.run("SELECT username, display_name, role, pw_hash, active FROM app_users WHERE username = %s",
                     (normalise(username),), fetch=True)
    if not rows:
        return None
    u, name, role, pw_hash, active = rows[0]
    return {"username": u, "display_name": name, "role": role, "pw_hash": pw_hash, "active": bool(active)}


def create_user(username: str, display_name: str, role: str, password: str) -> None:
    username = normalise(username)
    if not USERNAME_RE.match(username):
        raise ValueError("Username: 3-32 characters, lower-case letters, digits, dot, dash or underscore.")
    if role not in ("admin", "staff"):
        raise ValueError("Role must be admin or staff.")
    probs = password_problems(password, username)
    if probs:
        raise ValueError(" ".join(probs))
    if get_user(username):
        raise ValueError(f"User '{username}' already exists.")
    store.run("INSERT INTO app_users (username, display_name, role, pw_hash) VALUES (%s, %s, %s, %s)",
              (username, display_name.strip()[:80] or username, role, hash_password(password)))


def set_password(username: str, password: str) -> None:
    probs = password_problems(password, username)
    if probs:
        raise ValueError(" ".join(probs))
    n = store.run("UPDATE app_users SET pw_hash = %s, pw_changed_at = CURRENT_TIMESTAMP WHERE username = %s",
                  (hash_password(password), normalise(username)))
    if n != 1:
        raise ValueError("No such user.")


def set_active(username: str, active: bool) -> None:
    if store.run("UPDATE app_users SET active = %s WHERE username = %s", (bool(active), normalise(username))) != 1:
        raise ValueError("No such user.")


def list_users() -> list[dict]:
    rows = store.run("SELECT username, display_name, role, active, created_at, last_login_at FROM app_users ORDER BY username", fetch=True)
    return [dict(zip(["username", "display_name", "role", "active", "created_at", "last_login_at"], r)) for r in rows]


# ---------- sign-in ----------
def _record(username: str, success: bool, detail: str = "") -> None:
    store.run("INSERT INTO login_events (ts, username, success, detail) VALUES (%s, %s, %s, %s)",
              (time.time(), username[:64], bool(success), detail[:120]))


def recent_failures(username: str) -> int:
    """Wrong passwords in the last 15 minutes since the last successful sign-in. Attempts refused because of
    a lock are not counted, so a lock always ends 15 minutes after the fifth failure."""
    u = normalise(username)
    rows = store.run("SELECT COUNT(*) FROM login_events WHERE username = %s AND success = %s AND ts > %s AND detail <> 'locked' "
                     "AND ts > COALESCE((SELECT MAX(ts) FROM login_events WHERE username = %s AND success = %s), 0)",
                     (u, False, time.time() - LOCK_WINDOW_S, u, True), fetch=True)
    return int(rows[0][0])


def authenticate(username: str, password: str) -> tuple[dict | None, str]:
    """(user, "") on success, else (None, message). The message never says whether the username exists."""
    uname = normalise(username)
    if not uname or not password or len(password) > 256:
        return None, GENERIC_FAIL
    if recent_failures(uname) >= MAX_FAILS:
        _record(uname, False, "locked")
        return None, LOCKED_MSG
    user = get_user(uname) if USERNAME_RE.match(uname) else None
    ok = verify_password(password, user["pw_hash"] if user else _DUMMY_HASH)
    if not (user and ok and user["active"]):
        _record(uname, False, "bad credentials" if not user or not ok else "inactive")
        return None, GENERIC_FAIL
    _record(uname, True)
    store.run("UPDATE app_users SET last_login_at = CURRENT_TIMESTAMP WHERE username = %s", (uname,))
    return {k: user[k] for k in ("username", "display_name", "role")}, ""


def change_password(username: str, current: str, new: str) -> tuple[bool, str]:
    user = get_user(username)
    if not user or not verify_password(current, user["pw_hash"]):
        _record(normalise(username), False, "password change: wrong current password")
        return False, "Your current password is incorrect."
    if current == new:
        return False, "The new password must be different."
    probs = password_problems(new, username)
    if probs:
        return False, " ".join(probs)
    set_password(username, new)
    return True, "Password changed."


# ---------- per-user rate limits (in process; enough for a small staff tool) ----------
_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def allow(username: str, bucket: str, limit: int, window_s: int) -> bool:
    now = time.time()
    with _hits_lock:
        q = _hits[(username, bucket)]
        while q and q[0] < now - window_s:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


# ---------- Streamlit session ----------
def current_user(session) -> dict | None:
    """The signed-in user for this browser session, enforcing idle/absolute timeouts and account status."""
    a = session.get("auth")
    if not a:
        return None
    now = time.time()
    if now - a["last_active"] > IDLE_TIMEOUT_S or now - a["login_at"] > ABSOLUTE_TIMEOUT_S:
        sign_out(session, "Your session expired. Please sign in again.")
        return None
    if now - a["checked_at"] > RECHECK_S:
        try:
            u = get_user(a["username"])
        except Exception:  # noqa: BLE001 - database hiccup: keep the session, check again next run
            u = {"active": True, "role": a["role"]}
        if not u or not u["active"]:
            sign_out(session, "This account has been disabled.")
            return None
        a["role"], a["checked_at"] = u["role"], now
    a["last_active"] = now
    return a


def sign_in(session, user: dict) -> None:
    session.clear()  # fresh session state on every sign-in
    now = time.time()
    session["auth"] = {**user, "login_at": now, "last_active": now, "checked_at": now}


def sign_out(session, message: str = "") -> None:
    session.clear()
    if message:
        session["auth_message"] = message
