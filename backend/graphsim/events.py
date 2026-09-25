"""The event log: what happened, to whom, and why.

Every rule writes events here as it changes the world. The log is the source for the
inspector's history panel, so each event carries a human-readable `cause`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    tick: int
    kind: str  # short machine-readable label, e.g. "trade_started"
    subjects: tuple[str, ...]  # ids of the entities involved
    message: str  # e.g. "Alice started trading with Bob"
    cause: str = ""  # e.g. "Alice needed food; Bob had 6 spare"


class EventLog:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self._by_entity: dict[str, list[int]] = {}  # entity id -> indexes into self.events

    def add(
        self, tick: int, kind: str, subjects: tuple[str, ...], message: str, cause: str = ""
    ) -> Event:
        event = Event(tick, kind, subjects, message, cause)
        index = len(self.events)
        self.events.append(event)
        for entity_id in subjects:
            self._by_entity.setdefault(entity_id, []).append(index)
        return event

    def for_entity(self, entity_id: str) -> list[Event]:
        return [self.events[i] for i in self._by_entity.get(entity_id, [])]

    def since(self, index: int) -> list[Event]:
        """Events added after position `index` (use `len(log)` before a tick to get its events)."""
        return self.events[index:]

    def __len__(self) -> int:
        return len(self.events)
