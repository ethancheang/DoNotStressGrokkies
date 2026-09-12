"""
DoNotStress — Data Layer (data_manager)

Sole owner of flat-file persistence for fully evaluated student records.
Pure procedural Python: functions only — no classes.
No terminal I/O (print / input), no AI calls, no business-tier rules.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PACKAGE_ROOT = Path(__file__).resolve().parent
_DEFAULT_DATA_PATH = _PACKAGE_ROOT / "data" / "student_records.json"


def get_default_data_path() -> str:
    """Absolute path to the default JSON store."""
    return str(_DEFAULT_DATA_PATH)


def _resolve_path(data_path: str | None) -> Path:
    if data_path is None or str(data_path).strip() == "":
        return Path(get_default_data_path())
    return Path(data_path)


# ---------------------------------------------------------------------------
# Low-level load / save (graceful — never raise to callers for bad files)
# ---------------------------------------------------------------------------

def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_records_file(path: Path) -> tuple[bool, list[dict[str, Any]], str | None]:
    """
    Load records from JSON.
    Missing / empty / corrupt → (True, [], error_or_None) so callers never crash.
    ok is True when the app can continue; error explains soft failures.
    """
    if not path.exists():
        return True, [], None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return True, [], f"Could not read data file: {exc}"

    if raw.strip() == "":
        return True, [], None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return True, [], f"Corrupted JSON in data file: {exc}"

    if payload is None:
        return True, [], None

    if isinstance(payload, list):
        records = [r for r in payload if isinstance(r, dict)]
        return True, records, None

    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        records = [r for r in payload["records"] if isinstance(r, dict)]
        return True, records, None

    return True, [], "Data file JSON must be a list of records or an object with a 'records' list."


def _write_records_file(path: Path, records: list[dict[str, Any]]) -> tuple[bool, str | None]:
    try:
        _ensure_parent_dir(path)
        text = json.dumps(records, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")
        return True, None
    except OSError as exc:
        return False, f"Could not write data file: {exc}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_all_records(data_path: str | None = None) -> dict[str, Any]:
    """
    Load all historical records (for startup / reports).
    Returns {"ok": bool, "records": list, "error": str|None, "path": str}.
    Never raises on missing, empty, or corrupted files.
    """
    path = _resolve_path(data_path)
    ok, records, error = _read_records_file(path)
    return {
        "ok": ok,
        "records": records,
        "error": error,
        "path": str(path),
    }


def save_record(record: dict[str, Any], data_path: str | None = None) -> dict[str, Any]:
    """
    Append one fully evaluated student record (inputs + AI + tier).
    Adds saved_at (UTC ISO) if not already present.
    Returns {"ok": bool, "error": str|None, "path": str, "record": dict|None}.
    """
    if not isinstance(record, dict):
        return {
            "ok": False,
            "error": "record must be a dict",
            "path": str(_resolve_path(data_path)),
            "record": None,
        }

    path = _resolve_path(data_path)
    ok, records, load_error = _read_records_file(path)
    if not ok:
        return {"ok": False, "error": load_error, "path": str(path), "record": None}

    # Soft load errors (corrupt) still allow overwrite-with-append of a fresh valid list
    # so the app can recover; start from empty if previous content was unusable.
    if load_error and "Corrupted" in load_error:
        records = []

    stored = dict(record)
    if "saved_at" not in stored or not stored.get("saved_at"):
        stored["saved_at"] = datetime.now(timezone.utc).isoformat()

    records.append(stored)
    write_ok, write_error = _write_records_file(path, records)
    if not write_ok:
        return {"ok": False, "error": write_error, "path": str(path), "record": None}

    return {"ok": True, "error": None, "path": str(path), "record": stored}


def filter_records(records: list[dict[str, Any]], **filters: Any) -> list[dict[str, Any]]:
    """
    Pure in-memory filter. Supported keys:
      intervention_tier / tier, student_id, risk_category, cohort_year (2-digit prefix)
    Unknown keys are ignored. Missing fields on a record do not match.
    """
    if not isinstance(records, list):
        return []

    tier = filters.get("intervention_tier", filters.get("tier"))
    student_id = filters.get("student_id")
    risk_category = filters.get("risk_category")
    cohort_year = filters.get("cohort_year")

    out: list[dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if tier is not None:
            rec_tier = rec.get("intervention_tier", rec.get("tier"))
            try:
                if int(rec_tier) != int(tier):
                    continue
            except (TypeError, ValueError):
                continue
        if student_id is not None:
            if str(rec.get("student_id", "")) != str(student_id):
                continue
        if risk_category is not None:
            if str(rec.get("risk_category", "")).lower() != str(risk_category).lower():
                continue
        if cohort_year is not None:
            prefix = str(cohort_year).zfill(2)[-2:]
            sid = str(rec.get("student_id", ""))
            if len(sid) < 2 or sid[:2] != prefix:
                continue
        out.append(rec)
    return out


def get_records_by_tier(tier: int, data_path: str | None = None) -> list[dict[str, Any]]:
    loaded = load_all_records(data_path)
    return filter_records(loaded["records"], intervention_tier=tier)


def get_record_by_student_id(
    student_id: str, data_path: str | None = None
) -> list[dict[str, Any]]:
    """All historical rows for one student ID."""
    loaded = load_all_records(data_path)
    return filter_records(loaded["records"], student_id=student_id)


def get_records_by_risk_category(
    category: str, data_path: str | None = None
) -> list[dict[str, Any]]:
    loaded = load_all_records(data_path)
    return filter_records(loaded["records"], risk_category=category)


def get_records_by_cohort_year(
    year_prefix: str, data_path: str | None = None
) -> list[dict[str, Any]]:
    """Filter by student_id year prefix (e.g. '26' for 2026 intake)."""
    loaded = load_all_records(data_path)
    return filter_records(loaded["records"], cohort_year=year_prefix)
