"""What the browser session knows about its earlier submissions."""

from __future__ import annotations


class SubmissionContext:
    """The session owner and the pending row it already saved, if any.

    Built by the web layer from the session cookie so the check-in
    pipeline never touches Flask's session itself.
    """

    def __init__(self, owner: str, pending_fingerprint: str = "",
                 pending_record_id: str = "") -> None:
        self.__owner: str = owner
        self.__pending_fingerprint: str = pending_fingerprint
        self.__pending_record_id: str = pending_record_id.strip()

    @property
    def owner(self) -> str:
        """An opaque per-session key (the session's CSRF token)."""
        return self.__owner

    @property
    def pending_fingerprint(self) -> str:
        return self.__pending_fingerprint

    @property
    def pending_record_id(self) -> str:
        return self.__pending_record_id
