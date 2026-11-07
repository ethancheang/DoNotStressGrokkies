"""Every piece of student-facing wording the pages show."""

from __future__ import annotations

from json_types import JSONObject, JSONValue
from logic.trend import Trend


class StudentCopy:
    """Allow-listed wording for labels, tips, support and errors.

    Gemini only ever returns IDs; the text the student reads comes from
    here. Contacts are real SIT and national services and are never
    invented or taken from model output.
    """

    SOFT_LABEL_COPY: dict[str, dict[str, str]] = {
        "You're doing ok": {
            "heading": "You're doing ok",
            "body": "Your check-in looks steady. Keep looking after "
                    "yourself.",
            "tone": "reassuring",
        },
        "Worth a check-in": {
            "heading": "Worth a check-in",
            "body": "Some things look a bit heavier right now. A "
                    "conversation could help.",
            "tone": "supportive",
        },
        "Please reach out": {
            "heading": "Please reach out",
            "body": "Please reach out for support. You do not have to "
                    "handle this on your own.",
            "tone": "urgent",
        },
    }
    TIPS: dict[str, str] = {
        "sleep_routine": ("Try to keep a regular sleep schedule, including "
                          "on weekends."),
        "rest_a_little_more": ("If you can, give yourself a bit more rest — "
                               "even 30 extra minutes can help."),
        "short_breaks": ("Take short, planned breaks between study blocks "
                         "instead of pushing through without a pause."),
        "workload_chunks": ("Break larger assignments into smaller tasks "
                            "and spread them across the week."),
        "money_worries": ("If money is on your mind, campus support can "
                          "help you find the right next step."),
        "talk_to_someone": ("Reach out to a friend, classmate, or family "
                            "member — you do not have to handle this "
                            "alone."),
        "keep_social_contact": ("Stay in touch with people who help you "
                                "feel supported, even with a short "
                                "check-in."),
        "feelings_check_in": ("Name how you have been feeling and give "
                              "yourself permission to ask for help if "
                              "school feels heavy."),
    }
    ADVISOR_EMAIL: str = "SITCounselling@SingaporeTech.edu.sg"
    ADVISOR_HELPLINE: str = "6592 2030"
    ADVISOR_MAILTO: str = "mailto:SITCounselling@SingaporeTech.edu.sg"
    SOS_HELPLINE: str = "1767"
    MINDLINE_HELPLINE: str = "1771"
    SPEAK_PANEL_COPY: dict[str, dict[str, str]] = {
        "low": {
            "heading": "Support is available",
            "body": ("If you would like to talk, you can contact SIT "
                     "Counselling."),
            "cta": "Optional: get in touch",
        },
        "medium": {
            "heading": "Consider speaking with someone",
            "body": ("It may help to talk with SIT Counselling about how "
                     "you have been feeling."),
            "cta": "Reach out when you are ready",
        },
        "high": {
            "heading": "Please reach out",
            "body": ("Please contact SIT Counselling. You do not have to "
                     "handle this on your own."),
            "cta": "Contact support now",
        },
    }
    AI_ERROR_HEADING: str = "We couldn't complete your check-in"
    AI_ERROR_BODY: str = (
        "This check-in needs Gemini AI before we can show a result. AI is "
        "required for every record, so we cannot finish your check-in "
        "right now. Please try again later.")
    AI_RATE_LIMITED_BODY: str = (
        "Our check-in assistant is busy right now. Your answers have been "
        "saved and will be reviewed soon.")
    AI_ERROR_HINTS: dict[str, str] = {
        "missing_api_key": (
            "Operators/dev: GEMINI_API_KEY is not set. Add it to the "
            "environment and restart the app. Never paste the key into the "
            "page or into student-facing copy."),
        "timeout": (
            "Operators/dev: the Gemini request timed out. Confirm "
            "GEMINI_API_KEY is set and the service is reachable, then try "
            "again. Do not share the key."),
        "invalid_response": (
            "Operators/dev: Gemini returned a response that could not be "
            "used. Confirm GEMINI_API_KEY is set and check server logs. Do "
            "not expose the key."),
        "retries_exhausted": (
            "Operators/dev: Gemini failed after retries. Confirm "
            "GEMINI_API_KEY is set and the service is reachable. Do not "
            "expose the key."),
        "rate_limited": (
            "Operators/dev: every Gemini model was rate-limited. The "
            "check-in is saved as pending. Do not share the API key."),
        "unavailable": (
            "Operators/dev: Gemini AI is required for every check-in. "
            "Confirm GEMINI_API_KEY is set in the environment. Do not "
            "share or display the key."),
    }

    COMPARISON_COPY: dict[str, str] = {
        Trend.NONE: ("No finished check-ins yet. Your history starts with "
                     "your next check-in."),
        Trend.FIRST: ("This is your first finished check-in. Check in again "
                      "later to see how things change."),
        Trend.LOWER: "Your latest score is {change} points lower than last "
                     "time.",
        Trend.SIMILAR: "Your latest score is about the same as last time.",
        Trend.HIGHER: "Your latest score is {change} points higher than "
                      "last time.",
    }
    DIRECTION_COPY: dict[str, str] = {
        Trend.NOT_ENOUGH: ("After three check-ins, this page shows which way "
                           "things are heading."),
        Trend.EASING: ("Across your recent check-ins, stress looks like it "
                       "is easing."),
        Trend.STEADY: ("Across your recent check-ins, stress has stayed "
                       "fairly steady."),
        Trend.BUILDING: ("Across your recent check-ins, stress looks like it "
                         "is building. Talking to someone can help."),
    }

    def soft_label(self, label: str) -> JSONObject:
        """Heading, body and tone for one of the three soft labels."""
        copy = self.SOFT_LABEL_COPY.get(label.strip())
        if copy is None:
            allowed = ", ".join(f'"{name}"' for name in self.SOFT_LABEL_COPY)
            return {"label": "", "heading": "", "body": "", "tone": "",
                    "error": f"Unknown soft label. Use one of: {allowed}."}
        return {"label": label.strip(), **copy, "error": None}

    def tips(self, tip_ids: list[str]) -> JSONObject:
        """Allow-listed tip text for tip IDs, in order, without repeats.

        Unknown IDs are dropped; this never invents a tip.
        """
        items: list[JSONValue] = []
        seen: set[str] = set()
        for raw in tip_ids:
            tip_id = raw.strip()
            if tip_id in self.TIPS and tip_id not in seen:
                seen.add(tip_id)
                items.append({"id": tip_id, "text": self.TIPS[tip_id]})
        return {"heading": "Suggestions for you", "items": items}

    def advisor_panel(self, prominence: str) -> JSONObject:
        """The "talk to someone" panel. Prominence only changes the tone.

        An unknown prominence still shows every contact, with medium copy.
        """
        level = prominence.strip().lower()
        error = None
        if level not in self.SPEAK_PANEL_COPY:
            level = "medium"
            error = "Unknown speak_prominence. Use one of: low, medium, high."
        return {
            "prominence": level,
            **self.SPEAK_PANEL_COPY[level],
            "email": self.ADVISOR_EMAIL,
            "helpline": self.ADVISOR_HELPLINE,
            "sos": self.SOS_HELPLINE,
            "mindline": self.MINDLINE_HELPLINE,
            "mailto": self.ADVISOR_MAILTO,
            "error": error,
        }

    def trend_summary(self, trend: Trend) -> JSONObject:
        """Plain sentences for how the latest score compares and moves."""
        change = trend.change
        amount = f"{abs(change):.2f}" if change is not None else ""
        headline = self.COMPARISON_COPY[trend.comparison]
        return {
            "comparison": trend.comparison,
            "direction": trend.direction,
            "headline": headline.format(change=amount),
            "detail": self.DIRECTION_COPY[trend.direction],
            "latest": trend.latest,
            "previous": trend.previous,
            "change": change,
            "average": trend.average,
        }

    def ai_error(self, code: str, detail: str | None = None) -> JSONObject:
        """The page shown when the AI step could not finish.

        Never a Logic-only result. An unknown code still gets a full page
        with contacts, and sets "error".
        """
        known = code.strip().lower()
        error = None
        if known not in self.AI_ERROR_HINTS:
            if known:
                error = ("Unknown AI error_code. Use one of: "
                         f"{', '.join(self.AI_ERROR_HINTS)}.")
            known = "unavailable"
        body = (self.AI_RATE_LIMITED_BODY if known == "rate_limited"
                else self.AI_ERROR_BODY)
        hint = self.AI_ERROR_HINTS[known]
        reason = self.__operator_detail(detail)
        if reason:
            hint = f"{hint} Detail: {reason}."
        return {
            "heading": self.AI_ERROR_HEADING,
            "body": body,
            "hint": hint,
            "action_label": "Try again",
            "tone": "urgent",
            "ai_required": True,
            "error_code": known,
            "reason": reason,
            "speak_to_advisor": self.advisor_panel("high"),
            "error": error,
        }

    def __operator_detail(self, raw: str | None) -> str | None:
        """A short operator note, or None if it might hold a secret."""
        text = (raw or "").strip()
        if not text or self.__looks_like_secret(text):
            return None
        return text if len(text) <= 200 else text[:200].rstrip() + "…"

    def __looks_like_secret(self, text: str) -> bool:
        compact = "".join(text.split())
        lowered = compact.lower()
        if "api_key=" in lowered:
            return True
        if "bearer" in lowered and len(compact) > 20:
            return True
        # Long token-like strings (Google API keys are 39+ characters).
        return len(compact) >= 32 and compact.isalnum()
