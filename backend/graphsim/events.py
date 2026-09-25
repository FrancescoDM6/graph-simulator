"""The event log: what happened, to whom, and why.

Every rule writes events here as it changes the world. Each event has:
  - `cause`: a human-readable reason ("Bob had nothing to spare"), and
  - `caused_by`: ids of earlier events that contributed to it, so the viewer can walk a
    causal trail backwards (a trust jump <- a gift <- a starving agent <- a drought).

`caused_by` records the contributing causes the rules know about when they act. It is a trail
to follow, not proof: counterfactual questions are what the ablation experiments are for.

Routine events (every trade attempt) are marked `detail=True`: they make causal trails
complete, but the viewer's event feed hides them by default and batch runs don't store them.
"""

from dataclasses import dataclass

# Trade attempts that left the buyer without what it wanted (see rules/trade.py).
FAILED_PURCHASE_KINDS = ("no_offers", "no_surplus", "cannot_afford", "refused")
# Events that add or remove a social tie, or remove an agent with all its ties.
TIE_CHANGE_KINDS = ("met", "introduced", "tie_faded", "tie_dropped", "left")


@dataclass(frozen=True)
class Event:
    id: int  # position in the log
    tick: int
    kind: str  # short machine-readable label, e.g. "trade_started"
    subjects: tuple[str, ...]  # ids of the entities involved
    message: str  # e.g. "Alice started trading with Bob"
    cause: str = ""  # e.g. "Alice needed food; Bob had 6 spare"
    caused_by: tuple[int, ...] = ()  # ids of earlier events that led to this one
    detail: bool = False  # routine event, hidden from the main feed


class EventLog:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self._by_entity: dict[str, list[int]] = {}  # entity id -> event ids, oldest first

    def add(
        self,
        tick: int,
        kind: str,
        subjects: tuple[str, ...],
        message: str,
        cause: str = "",
        caused_by: tuple[int, ...] = (),
        detail: bool = False,
    ) -> Event:
        event = Event(len(self.events), tick, kind, subjects, message, cause, caused_by, detail)
        self.events.append(event)
        for entity_id in subjects:
            self._by_entity.setdefault(entity_id, []).append(event.id)
        return event

    def get(self, event_id: int) -> Event:
        return self.events[event_id]

    def for_entity(self, entity_id: str) -> list[Event]:
        return [self.events[i] for i in self._by_entity.get(entity_id, [])]

    def recent(
        self, entity_id: str, kinds: tuple[str, ...], since_tick: int = 0, limit: int = 5
    ) -> list[Event]:
        """The entity's latest events of the given kinds (newest first), back to `since_tick`."""
        found: list[Event] = []
        for event_id in reversed(self._by_entity.get(entity_id, [])):
            event = self.events[event_id]
            if event.tick < since_tick or len(found) >= limit:
                break
            if event.kind in kinds:
                found.append(event)
        return found

    def latest(self, entity_id: str, kinds: tuple[str, ...], since_tick: int = 0) -> Event | None:
        found = self.recent(entity_id, kinds, since_tick, limit=1)
        return found[0] if found else None

    def this_tick(self, tick: int) -> list[Event]:
        """Events logged during `tick` (it must be the latest tick)."""
        events: list[Event] = []
        for event in reversed(self.events):
            if event.tick != tick:
                break
            events.append(event)
        return events[::-1]

    def since(self, index: int) -> list[Event]:
        """Events added after position `index` (use `len(log)` before a tick to get its events)."""
        return self.events[index:]

    def __len__(self) -> int:
        return len(self.events)


def ids(events: list[Event | None]) -> tuple[int, ...]:
    """The ids of the events that exist, for `caused_by`."""
    return tuple(e.id for e in events if e is not None)
