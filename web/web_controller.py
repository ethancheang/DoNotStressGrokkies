"""The Flask routes: HTTP and session handling only."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import TYPE_CHECKING

from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, session, url_for)
from flask.typing import ResponseReturnValue
from werkzeug.exceptions import RequestEntityTooLarge

from checkins.check_in_job import CheckInJob
from checkins.check_in_outcome import CheckInOutcome
from checkins.submission_context import SubmissionContext
from json_types import JSONObject
from records.check_in_record import CheckInRecord
from storage.storage_error import StorageError
from web.admin_sessions import AdminSessions
from web.history_pass import HistoryPass
from web.result_store import ResultStore

if TYPE_CHECKING:
    from main import App


class WebController:
    """Registers every route on the Flask app and answers each request.

    It knows the App it serves (association) and calls into it for every
    check-in, record and page. The admin sessions, result store and
    history pass are created here and belong to this controller
    (composition).
    """

    CALM_FAILURE: str = ("We could not complete your check-in right now. "
                         "Your answers are still here; please try again.")
    HISTORY_LOCKED: str = (
        "To keep check-ins private, history is only shown for a Student ID "
        "that has checked in on this device. Complete a check-in here "
        "first.")

    def __init__(self, app: App, flask: Flask) -> None:
        self.__app: App = app
        self.__admin: AdminSessions = AdminSessions()
        self.__results: ResultStore = ResultStore()
        self.__history_pass: HistoryPass = HistoryPass(
            str(flask.config["SECRET_KEY"]))
        self.__register(flask)

    @property
    def admin_sessions(self) -> AdminSessions:
        return self.__admin

    @property
    def results(self) -> ResultStore:
        return self.__results

    # --- Student pages ---------------------------------------------------

    def home(self) -> ResponseReturnValue:
        return self.__render_campus()

    def retired_page(self) -> ResponseReturnValue:
        """Legacy URL from the removed garden page."""
        return redirect(url_for("checkin"))

    def submit_checkin(self) -> ResponseReturnValue:
        values = (request.get_json(silent=True) if request.is_json
                  else request.form)
        if not isinstance(values, Mapping):
            return jsonify(message="Please submit a check-in form."), 400
        io = self.__app.io
        safety = io.safety_fired(values.get("feelings_text", ""))
        ok, record = io.validate_student_form(values)
        if not ok:
            advisor = io.advisor_panel("high") if safety else None
            return jsonify(errors=record, safety_flag=safety,
                           advisor=advisor), 400
        self.__clear_result()
        job = self.__app.submit_checkin(record, self.__context(), safety)
        return jsonify(status=job.status, jobId=job.id,
                       statusUrl=url_for("checkin_status", job_id=job.id)
                       ), 202

    def checkin_status(self, job_id: str) -> ResponseReturnValue:
        """Still working (202), or the check-in's final response."""
        job = self.__app.jobs.get(job_id, str(session.get("csrf_token", "")))
        if job is None:
            return jsonify(message="This check-in has expired. Please start "
                           "a new check-in."), 404
        if not job.is_done:
            return jsonify(status=job.status, jobId=job.id), 202
        return self.__finished(job)

    def result(self) -> ResponseReturnValue:
        """Refreshing only reads the stored result; nothing is re-saved."""
        if self.__current_result() is None:
            return redirect(url_for("checkin"))
        return self.__render_campus("result")

    def save_checkin(self) -> ResponseReturnValue:
        """Every result is saved before it is shown, so this only confirms."""
        if self.__current_result() is None:
            return jsonify(message="Your result has expired. Please start "
                           "a new check-in."), 409
        return jsonify(ok=True, saved=True)

    def new_checkin(self) -> ResponseReturnValue:
        self.__clear_result()
        return redirect(url_for("checkin"))

    def history_page(self) -> ResponseReturnValue:
        return self.__render_campus("history")

    def lookup_history(self) -> ResponseReturnValue:
        """A student's own scores and trend, by Student ID.

        The ID must have checked in from this browser (or the viewer must
        be a signed-in admin), so typing a classmate's ID shows nothing.
        """
        values = (request.get_json(silent=True) if request.is_json
                  else request.form)
        form = values if isinstance(values, Mapping) else {}
        ok, student_id = self.__app.io.validate_student_id(
            form.get("student_id"))
        if not ok:
            return jsonify(message=student_id), 400
        cookie = request.cookies.get(HistoryPass.COOKIE_NAME)
        if not self.__is_admin() and not self.__history_pass.allows(
                cookie, student_id):
            return jsonify(message=self.HISTORY_LOCKED), 403
        try:
            page = self.__app.student_history(student_id)
        except StorageError:
            return jsonify(message="Your history could not be loaded. "
                           "Please try again."), 500
        return jsonify(history=page)

    # --- Admin pages -----------------------------------------------------

    def admin_login(self) -> ResponseReturnValue:
        if self.__is_admin():
            return redirect(url_for("records_page"))
        token = self.__csrf_token()
        error, status = None, 200
        if request.method == "POST":
            values = (request.get_json(silent=True) if request.is_json
                      else request.form)
            form = values if isinstance(values, Mapping) else {}
            address = request.remote_addr or "local"
            if not self.__admin.record_attempt(address):
                error, status = ("Too many sign-in attempts. Please try "
                                 "again in five minutes."), 429
            elif self.__admin.credentials_match(form.get("username", ""),
                                                form.get("password", "")):
                self.__admin.revoke(session.get("admin_token"))
                session["admin_token"] = self.__admin.issue(address)
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(url_for("records_page"))
            else:
                error, status = "Incorrect username or password.", 401
        page = render_template("admin_login.html", error=error,
                               csrf_token=token)
        return page, status

    def admin_logout(self) -> ResponseReturnValue:
        self.__admin.revoke(session.pop("admin_token", None))
        self.__clear_result()
        self.__app.forget_submission(str(session.get("csrf_token", "")))
        session.clear()
        return redirect(url_for("checkin"))

    def records_page(self) -> ResponseReturnValue:
        if not self.__is_admin():
            return redirect(url_for("admin_login"))
        return self.__render_campus("records")

    def saved_records(self) -> ResponseReturnValue:
        """Saved check-ins for staff; never free text or keys."""
        if not self.__is_admin():
            return jsonify(message="Admin sign-in is required to view "
                           "saved records."), 401
        tier = request.args.get("tier", "").strip()
        cohort = request.args.get("cohort_year", "").strip()
        problem = self.__app.io.validate_record_filters(tier, cohort)
        if problem:
            return jsonify(message=problem), 400
        try:
            page = self.__app.admin_records(
                tier, cohort, request.args.get("student_id", "").strip())
        except StorageError:
            return jsonify(message="Saved records could not be loaded. "
                           "Please try again."), 500
        return jsonify(page)

    # --- Service ---------------------------------------------------------

    def health(self) -> ResponseReturnValue:
        return jsonify(self.__app.health())

    def check_request(self) -> ResponseReturnValue | None:
        """Expire old state, then require the CSRF token on every POST."""
        self.__results.expire()
        self.__admin.expire()
        self.__app.jobs.expire()
        if request.method != "POST":
            return None
        expected = str(session.get("csrf_token", ""))
        provided = request.headers.get("X-CSRF-Token", "")
        if not provided and not request.is_json:
            provided = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(
                provided.encode("utf-8"), expected.encode("utf-8")):
            return jsonify(message="This page has expired. Reload and try "
                           "again."), 403
        return None

    def prevent_caching(self, response: Response) -> Response:
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    def too_large(self, error: RequestEntityTooLarge) -> ResponseReturnValue:
        return jsonify(message="Your response is too long. Please shorten "
                       "it and try again."), 413

    # --- Helpers ---------------------------------------------------------

    def __register(self, flask: Flask) -> None:
        flask.before_request(self.check_request)
        flask.after_request(self.prevent_caching)
        flask.register_error_handler(413, self.too_large)
        routes = (
            ("/", "checkin", self.home, ("GET",)),
            ("/", "submit_checkin", self.submit_checkin, ("POST",)),
            ("/checkin/status/<job_id>", "checkin_status",
             self.checkin_status, ("GET",)),
            ("/garden", "retired_page", self.retired_page, ("GET",)),
            ("/result", "result", self.result, ("GET",)),
            ("/save", "save_checkin", self.save_checkin, ("POST",)),
            ("/new", "new_checkin", self.new_checkin, ("GET",)),
            ("/admin/login", "admin_login", self.admin_login,
             ("GET", "POST")),
            ("/admin/logout", "admin_logout", self.admin_logout, ("POST",)),
            ("/records", "records_page", self.records_page, ("GET",)),
            ("/api/records", "saved_records", self.saved_records, ("GET",)),
            ("/history", "history_page", self.history_page, ("GET",)),
            ("/api/history", "lookup_history", self.lookup_history,
             ("POST",)),
            ("/health", "health", self.health, ("GET",)),
        )
        for rule, endpoint, view, methods in routes:
            flask.add_url_rule(rule, endpoint, view, methods=list(methods))

    def __finished(self, job: CheckInJob) -> ResponseReturnValue:
        outcome = job.outcome
        if outcome is None:
            return jsonify(message=self.CALM_FAILURE), 500
        return self.__respond(outcome, job.safety_flag)

    def __respond(self, outcome: CheckInOutcome,
                  safety: bool) -> Response:
        """Turn a pipeline outcome into the session update and response.

        Any saved check-in, finished or pending, unlocks that Student ID's
        history on this browser.
        """
        if outcome.status == CheckInOutcome.SAVE_FAILED:
            response = jsonify(message="We could not save your check-in "
                               "just now. Your answers are still here; "
                               "please try again.")
            response.status_code = 500
            return response
        if outcome.result is None:
            if outcome.saved:
                session["pending_fingerprint"] = outcome.fingerprint
                session["pending_record_id"] = outcome.record_id
            advisor = self.__app.io.display_error(outcome.error_code)[
                "speak_to_advisor"]
            response = jsonify(message=self.CALM_FAILURE,
                               error_code=outcome.error_code,
                               safety_flag=safety, advisor=advisor)
            response.status_code = 503
        else:
            session.pop("pending_fingerprint", None)
            session.pop("pending_record_id", None)
            session["checkin_token"] = self.__results.put(outcome.result)
            page = self.__app.io.display_result(
                CheckInRecord(outcome.result))
            response = jsonify(ok=True, result=page)
        if outcome.saved:
            self.__grant_history(response, outcome.student_id)
        return response

    def __grant_history(self, response: Response, student_id: str) -> None:
        held = request.cookies.get(HistoryPass.COOKIE_NAME)
        response.set_cookie(
            HistoryPass.COOKIE_NAME,
            self.__history_pass.grant(held, student_id),
            max_age=HistoryPass.MAX_AGE_SECONDS, httponly=True,
            samesite="Lax", secure=request.is_secure)

    def __render_campus(self, page: str = "home") -> str:
        csrf = self.__csrf_token()
        stored = self.__current_result()
        result = (self.__app.io.display_result(CheckInRecord(stored))
                  if stored is not None else None)
        return render_template("checkin.html", boot={
            "page": page,
            "survey": self.__app.io.page_config(),
            "isAdmin": self.__is_admin(),
            "adminLoginUrl": url_for("admin_login"),
            "result": result,
            "csrfToken": csrf,
            "submitUrl": url_for("submit_checkin"),
            "saveUrl": url_for("save_checkin"),
            "newUrl": url_for("new_checkin"),
            "homeUrl": url_for("checkin"),
            "resultUrl": url_for("result"),
            "recordsPageUrl": url_for("records_page"),
            "recordsUrl": url_for("saved_records"),
            "historyPageUrl": url_for("history_page"),
            "historyUrl": url_for("lookup_history"),
        })

    def __context(self) -> SubmissionContext:
        return SubmissionContext(
            str(session.get("csrf_token", "")),
            str(session.get("pending_fingerprint", "")),
            str(session.get("pending_record_id", "")))

    def __csrf_token(self) -> str:
        return str(session.setdefault("csrf_token", secrets.token_urlsafe(32)))

    def __is_admin(self) -> bool:
        if self.__admin.is_valid(session.get("admin_token")):
            return True
        session.pop("admin_token", None)
        return False

    def __current_result(self) -> JSONObject | None:
        return self.__results.get(session.get("checkin_token"))

    def __clear_result(self) -> None:
        self.__results.drop(session.pop("checkin_token", None))
