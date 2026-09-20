"""DoNotStress — student-facing Flask check-in app.

Wires the merged layers; does not reimplement their rules:

  1. io_manager.validate_student_form(...)
  2. ai_manager.analyse_student(...)  (Gemini when GEMINI_API_KEY is set)
  3. logic_manager.apply_soft_outcome(...)  (fallback; uses assign_soft_outcome)
  4. io_manager format_soft_label / format_tips / format_speak_to_advisor_panel
  5. data_manager.save_record(..., opt_in=True)  only after explicit consent
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import ai_manager
import data_manager
import io_manager
import logic_manager

logger = logging.getLogger(__name__)

SESSION_RECORD_KEY = "pending_record"
SESSION_SAVED_KEY = "checkin_saved"
GEMINI_SOURCE = "gemini"


def evaluate_checkin(
    record: dict[str, Any],
    *,
    generate_fn: Callable[[str, str, str], str] | None = None,
    max_attempts: int = 3,
    retry_delay_sec: float = 0.5,
) -> dict[str, Any]:
    """Run AI first; fall back to logic_manager soft outcomes."""
    ok, enriched, error = ai_manager.analyse_student(
        record,
        generate_fn=generate_fn,
        max_attempts=max_attempts,
        retry_delay_sec=retry_delay_sec,
    )
    if ok and isinstance(enriched, dict):
        result = dict(enriched)
        result.setdefault("source", GEMINI_SOURCE)
        return result

    logger.info("AI path unavailable; using logic fallback: %s", error)
    return logic_manager.apply_soft_outcome(record)


def _result_view(record: dict[str, Any]) -> dict[str, Any]:
    """Build template context from a evaluated record via io_manager formatters."""
    return {
        "soft": io_manager.format_soft_label(record.get("soft_label")),
        "tips": io_manager.format_tips(record.get("tips")),
        "advisor": io_manager.format_speak_to_advisor_panel(
            record.get("speak_prominence")
        ),
        "summary": io_manager.format_student_record(record),
        "saved": bool(session.get(SESSION_SAVED_KEY)),
    }


def _form_values(form=None) -> dict[str, str]:
    values = {key: "" for key in io_manager.FORM_FIELDS}
    if form is None:
        return values
    getter = getattr(form, "get", None)
    if getter is None:
        return values
    for key in io_manager.FORM_FIELDS:
        raw = getter(key)
        values[key] = "" if raw is None else str(raw)
    return values


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-insecure-donotstress"),
        DATA_PATH=os.environ.get("DONOTSTRESS_DATA_PATH") or None,
        AI_GENERATE_FN=None,
        AI_MAX_ATTEMPTS=int(os.environ.get("AI_MAX_ATTEMPTS", "3")),
        AI_RETRY_DELAY_SEC=float(os.environ.get("AI_RETRY_DELAY_SEC", "0.5")),
    )
    if test_config:
        app.config.update(test_config)

    @app.context_processor
    def inject_form_meta():
        return {
            "form_fields": io_manager.FORM_FIELDS,
            "form_prompts": io_manager.FORM_PROMPTS,
            "scale_min": io_manager.SCALE_MIN,
            "scale_max": io_manager.SCALE_MAX,
            "sleep_min": io_manager.SLEEP_HOURS_MIN,
            "sleep_max": io_manager.SLEEP_HOURS_MAX,
            "sleep_step": io_manager.SLEEP_HOURS_STEP,
            "student_id_example": io_manager.STUDENT_ID_EXAMPLE,
            "scale_fields": (
                "stress_level",
                "academic_workload",
                "financial_stress",
                "social_support",
            ),
        }

    @app.get("/")
    def checkin():
        return render_template(
            "checkin.html",
            values=_form_values(),
            errors={},
        )

    @app.post("/")
    def submit_checkin():
        ok, payload = io_manager.validate_student_form(request.form)
        if not ok:
            return render_template(
                "checkin.html",
                values=_form_values(request.form),
                errors=payload,
            ), 400

        record = evaluate_checkin(
            payload,
            generate_fn=app.config.get("AI_GENERATE_FN"),
            max_attempts=app.config.get("AI_MAX_ATTEMPTS", 3),
            retry_delay_sec=app.config.get("AI_RETRY_DELAY_SEC", 0.5),
        )
        session[SESSION_RECORD_KEY] = record
        session[SESSION_SAVED_KEY] = False
        return redirect(url_for("result"))

    @app.get("/result")
    def result():
        record = session.get(SESSION_RECORD_KEY)
        if not record:
            flash("Start with a check-in first.", "info")
            return redirect(url_for("checkin"))
        return render_template("result.html", **_result_view(record))

    @app.post("/save")
    def save_checkin():
        record = session.get(SESSION_RECORD_KEY)
        if not record:
            flash("Start with a check-in first.", "info")
            return redirect(url_for("checkin"))

        opted_in = request.form.get("opt_in")
        if not opted_in:
            flash(
                "Nothing was saved. Tick the box if you want to save this check-in.",
                "info",
            )
            return redirect(url_for("result"))

        saved = data_manager.save_record(
            record,
            data_path=app.config.get("DATA_PATH"),
            opt_in=True,
        )
        if saved.get("ok"):
            session[SESSION_SAVED_KEY] = True
            flash("Your check-in was saved on this computer.", "success")
        else:
            flash(saved.get("error") or "Could not save your check-in.", "error")
        return redirect(url_for("result"))

    @app.get("/new")
    def new_checkin():
        session.pop(SESSION_RECORD_KEY, None)
        session.pop(SESSION_SAVED_KEY, None)
        return redirect(url_for("checkin"))

    return app


app = create_app()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1").lower() not in {"0", "false", "no"}
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=debug)
