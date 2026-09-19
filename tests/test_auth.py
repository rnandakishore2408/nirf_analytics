"""Sign-in, passwords, lock-outs and sessions."""
from __future__ import annotations

import time

import pytest

import auth
import live_store


def test_hash_roundtrip_and_salting():
    h1, h2 = auth.hash_password("Correct-Horse-9"), auth.hash_password("Correct-Horse-9")
    assert h1 != h2, "each hash must use a fresh salt"
    assert "Correct-Horse-9" not in h1
    assert h1.startswith("scrypt$32768$8$1$")
    assert auth.verify_password("Correct-Horse-9", h1)
    assert not auth.verify_password("correct-horse-9", h1)
    assert not auth.verify_password("Correct-Horse-9", "garbage")
    assert not auth.verify_password("Correct-Horse-9", "bcrypt$1$2$3$4$5")


def test_password_policy():
    assert auth.password_problems("short")
    assert auth.password_problems("t.staff-is-my-password", "t.staff")
    assert auth.password_problems("password123")
    assert auth.password_problems("aaaaaaaaaaaa")
    assert auth.password_problems("x" * 129)
    assert auth.password_problems("Kp7m-Qx2r-T9vb") == []


def test_generated_passwords_are_strong_and_unique():
    pws = {auth.generate_password() for _ in range(200)}
    assert len(pws) == 200
    for pw in list(pws)[:20]:
        assert len(pw) == 19 and auth.password_problems(pw) == []


def test_sign_in_success_and_generic_failures(users, clean_live):
    user, msg = auth.authenticate("t.staff", users["t.staff"])
    assert user == {"username": "t.staff", "display_name": "Test Staff", "role": "staff"} and msg == ""
    assert "pw_hash" not in user
    # username is case/space insensitive
    assert auth.authenticate("  T.Staff ", users["t.staff"])[0] is not None
    wrong = auth.authenticate("t.staff", "not-the-password")
    unknown = auth.authenticate("nobody.here", "whatever-password")
    assert wrong == unknown == (None, auth.GENERIC_FAIL), "the message must not reveal whether a username exists"


@pytest.mark.parametrize("attempt", ["' OR '1'='1", "t.staff'--", "t.staff; DROP TABLE app_users;--", "", "a" * 500])
def test_sql_injection_and_junk_in_username(users, clean_live, attempt):
    assert auth.authenticate(attempt, "' OR '1'='1")[0] is None
    assert auth.get_user("t.staff") is not None, "tables must survive"


def test_lockout_after_five_failures_real_and_unknown(users, clean_live):
    for name in ("t.staff", "ghost.user"):
        for _ in range(auth.MAX_FAILS):
            assert auth.authenticate(name, "wrong-password-x")[1] == auth.GENERIC_FAIL
        assert auth.authenticate(name, "wrong-password-x")[1] == auth.LOCKED_MSG
    # even the right password is refused while locked
    assert auth.authenticate("t.staff", users["t.staff"]) == (None, auth.LOCKED_MSG)
    # a different user is unaffected
    assert auth.authenticate("t.other", users["t.other"])[0] is not None


def test_lock_ends_after_window_even_if_attacker_keeps_trying(users, clean_live):
    for _ in range(auth.MAX_FAILS):
        auth.authenticate("t.staff", "wrong-password-x")
    for _ in range(10):  # hammering during the lock must not extend it
        assert auth.authenticate("t.staff", "wrong-password-x")[1] == auth.LOCKED_MSG
    live_store.run("UPDATE login_events SET ts = ts - %s WHERE detail <> 'locked'", (auth.LOCK_WINDOW_S + 1,))
    assert auth.authenticate("t.staff", users["t.staff"])[0] is not None


def test_success_resets_failure_count(users, clean_live):
    for _ in range(auth.MAX_FAILS - 1):
        auth.authenticate("t.staff", "wrong-password-x")
    assert auth.authenticate("t.staff", users["t.staff"])[0] is not None
    assert auth.recent_failures("t.staff") == 0


def test_disabled_account_cannot_sign_in(users, clean_live):
    auth.set_active("t.other", False)
    try:
        assert auth.authenticate("t.other", users["t.other"]) == (None, auth.GENERIC_FAIL)
    finally:
        auth.set_active("t.other", True)


def test_every_attempt_is_logged_without_passwords(users, clean_live):
    auth.authenticate("t.staff", "Secret-Guess-123")
    auth.authenticate("t.staff", users["t.staff"])
    rows = live_store.run("SELECT username, success, detail FROM login_events ORDER BY id", fetch=True)
    assert [(r[0], bool(r[1])) for r in rows] == [("t.staff", False), ("t.staff", True)]
    assert all("Secret" not in (r[2] or "") and users["t.staff"] not in (r[2] or "") for r in rows)


def test_change_password(users, clean_live):
    old = users["t.other"]
    assert auth.change_password("t.other", "wrong-current", "New-Pass-4321x") == (False, "Your current password is incorrect.")
    assert not auth.change_password("t.other", old, "short")[0]
    assert not auth.change_password("t.other", old, old)[0]
    assert auth.change_password("t.other", old, "New-Pass-4321x") == (True, "Password changed.")
    assert auth.authenticate("t.other", old)[0] is None
    assert auth.authenticate("t.other", "New-Pass-4321x")[0] is not None
    auth.set_password("t.other", old)


def test_account_creation_rules(users):
    for bad in ("ab", "Bad Name", "x'--", "a" * 40, "-lead"):
        with pytest.raises(ValueError):
            auth.create_user(bad, "X", "staff", "Fine-Password-77")
    with pytest.raises(ValueError):
        auth.create_user("t.staff", "Dup", "staff", "Fine-Password-77")
    with pytest.raises(ValueError):
        auth.create_user("new.user", "X", "superuser", "Fine-Password-77")
    with pytest.raises(ValueError):
        auth.create_user("new.user", "X", "staff", "weak")


def test_session_timeouts_and_disable_recheck(users):
    s: dict = {}
    auth.sign_in(s, {"username": "t.other", "display_name": "Test Other", "role": "staff"})
    assert auth.current_user(s)["username"] == "t.other"
    s["auth"]["last_active"] -= auth.IDLE_TIMEOUT_S + 1
    assert auth.current_user(s) is None and "expired" in s["auth_message"]

    auth.sign_in(s, {"username": "t.other", "display_name": "Test Other", "role": "staff"})
    s["auth"]["login_at"] -= auth.ABSOLUTE_TIMEOUT_S + 1
    assert auth.current_user(s) is None

    auth.sign_in(s, {"username": "t.other", "display_name": "Test Other", "role": "staff"})
    auth.set_active("t.other", False)
    try:
        s["auth"]["checked_at"] -= auth.RECHECK_S + 1
        assert auth.current_user(s) is None and "disabled" in s["auth_message"]
    finally:
        auth.set_active("t.other", True)


def test_sign_in_clears_previous_session_state():
    s = {"leftover": "from another user", "auth": {"username": "x"}}
    auth.sign_in(s, {"username": "t.staff", "display_name": "S", "role": "staff"})
    assert "leftover" not in s and s["auth"]["username"] == "t.staff"
    auth.sign_out(s)
    assert s == {}


def test_rate_limiter():
    key = f"rl-{time.time()}"
    assert all(auth.allow(key, "b", 3, 60) for _ in range(3))
    assert not auth.allow(key, "b", 3, 60)
    assert auth.allow(key, "other-bucket", 3, 60)


def test_unknown_usernames_cost_the_same_hash_work(users, clean_live):
    def timed(u):
        t = time.perf_counter(); auth.authenticate(u, "wrong-password-x"); return time.perf_counter() - t  # noqa: E702
    known = min(timed("t.admin") for _ in range(2))
    live_store.run("DELETE FROM login_events")
    unknown = min(timed("no.such.user") for _ in range(2))
    assert unknown > 0.3 * known, "unknown usernames must still run the password hash"
