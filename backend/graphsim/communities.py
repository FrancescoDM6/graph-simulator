"""Communities with an identity over time: who belongs to which group, and how groups are born,
split, merge and die.

Louvain finds communities afresh every time it runs and numbers them arbitrarily. To follow a
community through time, each detection is matched to the previous one by member overlap:

  continuation  a new community whose Jaccard overlap with a living one is at least
                `community_match_jaccard` keeps that community's id (best overlaps first);
  split         an unmatched new community whose members mostly came from one living community
                is born as its child;
  birth         any other unmatched new community is simply new;
  merger        an unmatched old community whose members mostly ended up in one new community
                dies, "merged into" it;
  break-up      an old community whose members mostly went to one of its own children dies,
                having split;
  dissolution   any other unmatched old community dies.

"Mostly" means more than half. Records of every community ever seen live in
world.metrics.communities; analysis.py turns them into lifespans, turnover, splits and mergers.
"""

import networkx as nx

from graphsim.events import TIE_CHANGE_KINDS, ids
from graphsim.model import World
from graphsim.stats import CommunityRecord

MAJORITY = 0.5


def update_communities(world: World, social: nx.Graph) -> dict[str, int]:
    """Detects communities, carries identities forward, logs changes; returns agent -> id."""
    min_size = world.cfg.metrics.min_community_size
    found = [c for c in louvain(social) if len(c) >= min_size]
    return track_communities(world, found, social)


def track_communities(world: World, found: list[set[str]], social: nx.Graph) -> dict[str, int]:
    """Matches this detection's communities to the living ones (rules in the module docstring)."""
    cfg = world.cfg.metrics
    state = world.metrics
    found = sorted(found, key=lambda c: (-len(c), min(c)))  # biggest first, deterministic
    alive = {cid: state.communities[cid] for cid in state.alive}
    quiet = state.detections == 0  # everything is "new" at the first detection; don't log that

    # 1. Continuations: the best-overlapping (old, new) pairs keep the old id.
    pairs = sorted(
        (
            (-jaccard(record.members, members), cid, i)
            for cid, record in alive.items()
            for i, members in enumerate(found)
            if record.members & members
        ),
    )
    id_of: dict[int, int] = {}  # index into `found` -> community id
    continued: set[int] = set()
    for negative_overlap, cid, i in pairs:
        if -negative_overlap < cfg.community_match_jaccard:
            break
        if cid not in continued and i not in id_of:
            id_of[i] = cid
            continued.add(cid)

    # 2. Unmatched new communities: splits (children of a living community) or births.
    children: dict[int, int] = {}  # new child id -> parent id
    for i, members in enumerate(found):
        if i in id_of:
            continue
        parent = _mostly_from(members, alive)
        record = _new_record(world, members, parent)
        id_of[i] = record.id
        if parent is not None:
            children[record.id] = parent
            if not quiet:
                _log_split(world, record, alive[parent], members)
        elif not quiet:
            _log_formed(world, record, members, social)

    # 3. Unmatched old communities die: merged, broken up into children, or dissolved.
    for cid in sorted(alive):
        if cid in continued:
            continue
        record = alive[cid]
        record.died = world.tick
        destination = _mostly_into(record.members, found)
        destination_id = id_of[destination] if destination is not None else None
        if destination_id is not None and children.get(destination_id) == cid:
            record.fate = "split"  # its children's "community_split" events tell the story
        elif destination_id is not None:
            record.fate = "merged"
            record.merged_into = destination_id
            _log_merged(world, record, destination_id)
        else:
            record.fate = "dissolved"
            _log_dissolved(world, record)

    # 4. Bring every living community's record up to date.
    for i, cid in id_of.items():
        record = state.communities[cid]
        if cid in continued:
            record.turnover_total += 1 - jaccard(record.members, found[i])
            record.continuations += 1
        record.members = set(found[i])
        record.members_ever |= found[i]
        record.peak_size = max(record.peak_size, len(found[i]))
        record.last_seen = world.tick

    state.alive = sorted(id_of.values())
    state.detections += 1
    return {agent_id: cid for i, cid in id_of.items() for agent_id in found[i]}


def entity_id(community_id: int) -> str:
    """How a community appears among an event's subjects, e.g. "community-3"."""
    return f"community-{community_id}"


def louvain(social: nx.Graph) -> list[set[str]]:
    # Louvain iterates over sets internally. Sets of strings iterate in an order that changes
    # between Python processes (hash randomization), so run it on integer node labels instead.
    numbered = nx.convert_node_labels_to_integers(social, label_attribute="agent_id")
    communities = nx.community.louvain_communities(numbered, weight="strength", seed=0)
    return [{numbered.nodes[n]["agent_id"] for n in c} for c in communities]


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _mostly_from(members: set[str], alive: dict[int, CommunityRecord]) -> int | None:
    """The living community that more than half of these members came from, if any."""
    for cid in sorted(alive):
        if len(members & alive[cid].members) > MAJORITY * len(members):
            return cid
    return None


def _mostly_into(members: set[str], found: list[set[str]]) -> int | None:
    """Index of the new community that more than half of these members ended up in, if any."""
    for i, new_members in enumerate(found):
        if len(members & new_members) > MAJORITY * len(members):
            return i
    return None


def _new_record(world: World, members: set[str], parent: int | None) -> CommunityRecord:
    state = world.metrics
    record = CommunityRecord(
        id=state.next_community_id,
        born=world.tick,
        parent=parent,
        members=set(members),
        members_ever=set(members),
        peak_size=len(members),
        last_seen=world.tick,
    )
    state.next_community_id += 1
    state.communities[record.id] = record
    return record


# --- events -----------------------------------------------------------------------------------


def _tie_changes_among(world: World, members: set[str], limit: int = 8) -> tuple[int, ...]:
    """This tick's events that added or removed ties involving the community's members."""
    changes = [
        e
        for e in world.log.this_tick(world.tick)
        if e.kind in TIE_CHANGE_KINDS and members & set(e.subjects)
    ]
    return ids(changes[:limit])


def _log_formed(world: World, record: CommunityRecord, members: set[str], social: nx.Graph):
    degree = {m: social.degree(m) if m in social else 0 for m in members}
    hubs = sorted(sorted(members), key=lambda m: -degree[m])[:3]
    world.log.add(
        world.tick,
        "community_formed",
        (entity_id(record.id), *sorted(members)),
        f"Community {record.id} formed around {', '.join(world.name(h) for h in hubs)}",
        cause=f"{len(members)} agents became more tied to each other than to outsiders",
        caused_by=_tie_changes_among(world, members),
    )


def _log_split(
    world: World, record: CommunityRecord, parent: CommunityRecord, members: set[str]
) -> None:
    from_parent = len(members & parent.members)
    world.log.add(
        world.tick,
        "community_split",
        (entity_id(record.id), entity_id(parent.id), *sorted(members)),
        f"Community {record.id} split off from community {parent.id}",
        cause=f"{from_parent} of its {len(members)} members came from community {parent.id}",
        caused_by=_tie_changes_among(world, members),
    )


def _log_merged(world: World, record: CommunityRecord, destination_id: int) -> None:
    still_here = sorted(m for m in record.members if m in world.agents)
    world.log.add(
        world.tick,
        "community_merged",
        (entity_id(record.id), entity_id(destination_id), *still_here),
        f"Community {record.id} merged into community {destination_id}",
        cause=f"most of its {len(record.members)} members are now in community {destination_id}",
        caused_by=_tie_changes_among(world, record.members),
    )


def _log_dissolved(world: World, record: CommunityRecord) -> None:
    members = record.members
    still_here = sorted(m for m in members if m in world.agents)
    world.log.add(
        world.tick,
        "community_dissolved",
        (entity_id(record.id), *still_here),
        f"Community {record.id} broke apart",
        cause=f"{len(members) - len(still_here)} of its {len(members)} members left the world; "
        "the rest's ties weakened or scattered across other groups",
        caused_by=_tie_changes_among(world, members),
    )
