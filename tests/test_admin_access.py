"""Authentication boundaries for saved student check-ins; synthetic data."""
import unittest
from unittest.mock import patch

from data_manager import DataManager
from helpers import (ADMIN_PASSWORD, campus, csrf_token, login_admin,
                     static_text)
from plain_tests import function_suite


def test_student_is_default_and_navigation_hides_records():
    with campus() as ctx:
        text = ctx.client.get("/").get_data(as_text=True)
        assert "Student view" in text
        assert "Admin sign in" in text
        assert "/ campus" not in text
        assert ">Home<" in text
        assert ">Overview<" not in text
        assert "Need to talk?" in text
        assert "A guide, not a diagnosis." in text
        assert ("Immediate crises: If you face an urgent emergency outside "
                "of school hours, you can use the 24-hour helpline (6592 "
                "2030) or reach out to national helplines such as "
                "Samaritans of Singapore (1-767) or emergency services "
                "(995 / 999).") in text
        assert 'href="tel:65922030"' in text
        assert 'href="tel:1767"' in text
        assert 'href="tel:1771"' in text
        assert 'href="mailto:SITCounselling@SingaporeTech.edu.sg"' in text
        assert 'class="ds-brand"' in text
        assert 'data-nav="records"' not in text
        assert "My garden" not in text
        assert '"isAdmin": false' in text
        assert ADMIN_PASSWORD not in text
        assert "scrypt:" not in text


def test_direct_page_redirects_and_api_never_reads_records():
    with campus() as ctx, patch.object(DataManager, "load") as load:
        response = ctx.client.get("/api/records?student_id=26&role=admin")
        assert response.status_code == 401
        assert "records" not in response.json
        load.assert_not_called()
        assert response.headers["Cache-Control"] == "no-store"
        assert ctx.client.get("/records").location.endswith("/admin/login")


def test_login_and_logout_require_csrf():
    with campus() as ctx:
        ctx.client.get("/admin/login")
        credentials = {"username": "admin", "password": ADMIN_PASSWORD}
        assert ctx.client.post("/admin/login", data=credentials
                               ).status_code == 403
        assert ctx.client.post("/admin/login", data={
            "csrf_token": "非ASCII"}).status_code == 403
        login_admin(ctx.client)
        assert ctx.client.post("/admin/logout").status_code == 403
        assert ctx.client.get("/admin/logout").status_code == 405
        assert ctx.client.get("/records").status_code == 200


def test_bad_credentials_and_malformed_payloads():
    with campus() as ctx:
        ctx.client.get("/admin/login")
        for body in ({"username": "admin", "password": "wrong"},
                     {"username": "student", "password": ADMIN_PASSWORD},
                     {"username": "admin", "password": [ADMIN_PASSWORD]},
                     {"username": "admin", "password": "x" * 300}, []):
            response = ctx.client.post(
                "/admin/login", json=body,
                headers={"X-CSRF-Token": csrf_token(ctx.client)})
            assert response.status_code == 401
            assert ctx.client.get("/api/records").status_code == 401


def test_admin_sees_records_and_new_client_stays_student():
    with campus() as ctx:
        response = login_admin(ctx.client)
        assert response.location.endswith("/records")
        text = ctx.client.get("/records").get_data(as_text=True)
        assert "Admin view" in text
        assert "Sign out" in text
        assert 'data-nav="records"' in text
        assert ADMIN_PASSWORD not in text
        with patch.object(DataManager, "load", return_value=[]):
            assert ctx.client.get("/api/records").status_code == 200
        fresh = ctx.app.flask.test_client()
        assert fresh.get("/api/records").status_code == 401


def test_admin_keeps_records_from_home_without_signing_in_again():
    with campus() as ctx:
        login_admin(ctx.client)
        home = ctx.client.get("/").get_data(as_text=True)
        assert "Admin view" in home
        assert "Sign out" in home
        assert 'data-nav="records"' in home
        assert "Admin sign in" not in home
        assert 'data-nav="home"' in home
        records = ctx.client.get("/records")
        assert records.status_code == 200
        assert 'data-nav="records"' in records.get_data(as_text=True)


def test_untrusted_role_and_unknown_server_token_do_not_authorize():
    with campus() as ctx:
        with ctx.client.session_transaction() as state:
            state["role"] = "admin"
            state["is_admin"] = True
            state["admin_token"] = "invented-token"
        response = ctx.client.get("/api/records", headers={"X-Role": "admin"})
        assert response.status_code == 401


def test_logout_revokes_old_cookie_and_returns_student():
    with campus() as ctx:
        login_admin(ctx.client)
        old_cookie = ctx.client.get_cookie("session").value
        response = ctx.client.post(
            "/admin/logout", data={"csrf_token": csrf_token(ctx.client)},
            follow_redirects=True)
        assert "Student view" in response.get_data(as_text=True)
        assert 'data-nav="records"' not in response.get_data(as_text=True)
        assert ctx.app.web.admin_sessions.active_count == 0
        ctx.client.set_cookie("session", old_cookie)
        assert ctx.client.get("/api/records").status_code == 401


def test_admin_expiry():
    with campus() as ctx:
        login_admin(ctx.client)
        ctx.app.web.admin_sessions.session_seconds = -1
        assert ctx.client.get("/api/records").status_code == 401
        assert ctx.client.get("/records").location.endswith("/admin/login")


def test_login_throttle_expires():
    with campus() as ctx:
        ctx.client.get("/admin/login")
        body = {"username": "admin", "password": "wrong",
                "csrf_token": csrf_token(ctx.client)}
        for _ in range(5):
            assert ctx.client.post("/admin/login", data=body
                                   ).status_code == 401
        assert ctx.client.post("/admin/login", data=body).status_code == 429
        ctx.app.web.admin_sessions.window_seconds = -1
        login_admin(ctx.client)


def test_password_not_echoed_or_embedded_in_static_assets():
    with campus() as ctx:
        text = ctx.client.get("/admin/login").get_data(as_text=True)
        assert 'type="password"' in text
        assert "/ campus" not in text
        assert ">Home<" in text
        assert ">Overview<" not in text
        assert ADMIN_PASSWORD not in text
        assert ADMIN_PASSWORD not in static_text("campus.js")


def test_login_rotates_csrf():
    with campus() as ctx:
        old = csrf_token(ctx.client)
        login_admin(ctx.client)
        assert old != csrf_token(ctx.client)


def load_tests(loader, tests, pattern):
    """Let `python -m unittest discover -s tests` run this file's tests."""
    return function_suite(globals())


if __name__ == "__main__":
    unittest.main()
