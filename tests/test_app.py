"""End-to-end through the real Streamlit app (headless): the sign-in gate, every page, and the
save -> recompute -> forecast flow."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import live_store

APP = str(Path(__file__).resolve().parents[1] / "app" / "Home.py")
PAGES = ["views/overview.py", "views/explorer.py", "views/position.py", "views/what_if.py", "views/prediction.py",
         "views/live_entry.py", "views/ask.py", "views/account.py"]


def fresh() -> AppTest:
    return AppTest.from_file(APP, default_timeout=180).run()


def sign_in(at: AppTest, username: str, password: str) -> AppTest:
    at.text_input[0].input(username)
    at.text_input[1].input(password)
    at.button[0].click().run()
    return at


def titles(at: AppTest) -> list[str]:
    return [t.value for t in at.title]


def all_text(at: AppTest) -> str:
    return " ".join([m.value for m in at.markdown] + [m.value for m in at.caption] + [e.value for e in at.error]
                    + [s.value for s in at.success] + [i.value for i in at.info] + [w.value for w in at.warning])


def test_signed_out_visitors_only_see_the_sign_in_form(users):
    at = fresh()
    assert not at.exception
    assert [t.label for t in at.text_input] == ["Username", "Password"]
    assert "no sign-up" in all_text(at).lower() or "There is no sign-up" in all_text(at)
    assert not titles(at), "no dashboard content before sign-in"
    for page in PAGES:  # pages are not registered, so asking for one still lands on the sign-in form
        try:
            at.switch_page(page).run()
        except Exception:  # noqa: BLE001 - AppTest refuses unknown pages outright, which is also a pass
            continue
        assert not titles(at) and [t.label for t in at.text_input] == ["Username", "Password"], page


def test_wrong_password_is_refused(users, clean_live):
    at = sign_in(fresh(), "t.staff", "definitely-wrong")
    assert any("Incorrect username or password" in e.value for e in at.error)
    assert not titles(at)


def test_every_page_renders_for_staff(users, clean_live):
    at = sign_in(fresh(), "t.staff", users["t.staff"])
    assert titles(at) == ["NIRF Analytics — Saveetha Engineering College"]
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, (page, [e.message for e in at.exception])
        assert titles(at), page


def _set(at: AppTest, key: str, value: float) -> None:
    at.number_input(key=f"in_{key}").set_value(value)


def test_saving_publications_recomputes_everywhere(users, clean_live):
    at = sign_in(fresh(), "t.staff", users["t.staff"])
    at.switch_page("views/prediction.py").run()
    before = all_text(at)
    assert "Includes staff-entered data" not in before

    at.switch_page("views/live_entry.py").run()
    _set(at, "scopus_publications_3y", 3000)
    _set(at, "scopus_citations_3y", 45000)
    _set(at, "phd_pursuing_ft", 120)
    [b for b in at.button if b.label == "Save entries"][0].click().run()
    assert not at.exception
    assert any("Saved 3 value(s)" in s.value for s in at.success), all_text(at)

    rows = live_store.history(10)
    assert set(rows.metric) == {"scopus_publications_3y", "scopus_citations_3y", "phd_pursuing_ft"}
    assert set(rows.username) == {"t.staff"} and set(rows.entered_by) == {"Test Staff"}, "author comes from the session"

    at.switch_page("views/prediction.py").run()
    assert "Includes staff-entered data: 3 metric(s)" in all_text(at)
    at.switch_page("views/overview.py").run()
    assert "incl. staff data" in " ".join(m.value for m in at.markdown)


def test_invalid_entries_are_not_saved(users, clean_live):
    at = sign_in(fresh(), "t.staff", users["t.staff"])
    at.switch_page("views/live_entry.py").run()
    _set(at, "students_female", 9000)  # filed total is 5,961
    [b for b in at.button if b.label == "Save entries"][0].click().run()
    assert any("Nothing was saved" in e.value for e in at.error)
    assert live_store.history(10).empty


def test_sign_out_returns_to_the_gate(users, clean_live):
    at = sign_in(fresh(), "t.admin", users["t.admin"])
    assert titles(at)
    [b for b in at.sidebar.button if b.label == "Sign out"][0].click().run()
    assert not titles(at) and any("signed out" in i.value for i in at.info)


@pytest.mark.parametrize("who", ["t.staff", "t.admin"])
def test_account_page_shows_the_signed_in_user(users, clean_live, who):
    at = sign_in(fresh(), who, users[who])
    at.switch_page("views/account.py").run()
    assert f"username `{who}`" in all_text(at)
