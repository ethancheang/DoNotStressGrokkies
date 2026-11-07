"""The contract every page presenter follows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from json_types import JSONObject
from records.record import Record


class View(ABC):
    """Turns one record into the plain data a page needs.

    Every view accepts any Record. render_many works the same for every
    view, so callers can swap one view for another without branching.
    """

    @abstractmethod
    def render(self, record: Record) -> JSONObject:
        """Page data for one record. Never includes reflection text."""

    def render_many(self, records: Sequence[Record]) -> list[JSONObject]:
        return [self.render(record) for record in records]
