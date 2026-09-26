"""Generated worlds: maps written from a few parameters instead of town by town.

A generator returns exactly the tables a written-out scenario contains ([world] towns with a
position, sites and founding people, and roads), so everything after it (validation, the run,
the viewer) treats generated and written-out worlds alike. Generators are deterministic: a map
depends only on its parameters, never on a run's seed, so seeds vary what agents do, not where
they live.

Every generator spreads the same totals (scenario.toml [layout]): the same number of people in
each occupation and the same total capacity of each site kind. Worlds then differ in shape
only, not in size or wealth of resources.

    [generator]
    name = "two_regions"
    towns_per_region = 2
    bridges = 1
    resources = "balanced"
"""

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from graphsim.config import LayoutSpec

# Town names, used in order. Plain made-up names, so no map suggests a real place.
TOWN_NAMES = [
    "Crossway", "Ashby", "Brookfield", "Dunmere", "Eastholm", "Fairlow", "Glenrock", "Hartwell",
    "Ivydale", "Kestrel", "Longmead", "Marsh End", "Northby", "Oakridge", "Pinecroft", "Redcliff",
]  # fmt: skip


class GeneratorError(ValueError):
    """A generator's parameters don't make a valid map."""


@dataclass
class Town:
    """A town being drafted."""

    name: str
    position: tuple[float, float]
    site_kinds: list[str] = field(default_factory=list)
    founding: dict[str, int] = field(default_factory=dict)


# --- The generators --------------------------------------------------------------------------


def hub_and_spokes(
    layout: "LayoutSpec", occupations: dict[str, Any], spokes: int
) -> dict[str, Any]:
    """A central market town joined by a road to each of `spokes` outlying towns, which hold
    the sites (kinds alternating around the ring). No road joins two spokes; every merchant lives
    in the hub, so all trade between spokes goes through it."""
    kinds = list(layout.site_capacity)
    if spokes < len(kinds):
        raise GeneratorError(
            f"hub_and_spokes: needs at least {len(kinds)} spokes (one per site kind)"
        )
    hub = Town(TOWN_NAMES[0], (0.5, 0.5))
    ring = []
    for i in range(spokes):
        angle = -math.pi / 2 + 2 * math.pi * i / spokes
        town = Town(TOWN_NAMES[1 + i], (0.5 + 0.38 * math.cos(angle), 0.5 + 0.38 * math.sin(angle)))
        town.site_kinds.append(kinds[i % len(kinds)])
        ring.append(town)
    towns = [hub, *ring]
    place_people(towns, layout, occupations, others_in=[hub])
    return world_tables(towns, [(hub, spoke) for spoke in ring], layout)


def two_regions(
    layout: "LayoutSpec",
    occupations: dict[str, Any],
    towns_per_region: int,
    bridges: int,
    resources: str,
    merchants: str,
) -> dict[str, Any]:
    """Two regions of `towns_per_region` towns, every town joined to every other in its region,
    and `bridges` roads across. resources = "balanced": each region has every site kind;
    "split": the West has the first site kind (farms) and the East all the others (mines).
    merchants: where they live (see place_merchants_two_regions)."""
    n = towns_per_region
    if n < 1:
        raise GeneratorError("two_regions: towns_per_region must be at least 1")
    if not 1 <= bridges <= n * n:
        raise GeneratorError(f"two_regions: bridges must be between 1 and {n * n}")
    if resources not in ("balanced", "split"):
        raise GeneratorError('two_regions: resources must be "balanced" or "split"')
    if merchants not in ("bridge_towns", "every_town"):
        raise GeneratorError('two_regions: merchants must be "bridge_towns" or "every_town"')
    west = [Town(TOWN_NAMES[i], (0.2, (i + 1) / (n + 1))) for i in range(n)]
    east = [Town(TOWN_NAMES[n + i], (0.8, (i + 1) / (n + 1))) for i in range(n)]
    kinds = list(layout.site_capacity)
    if resources == "balanced":
        _spread_kinds(west, kinds)
        _spread_kinds(east, kinds)
    else:
        _spread_kinds(west, kinds[:1])
        _spread_kinds(east, kinds[1:] or kinds[:1])

    inside = [
        (a, b) for region in (west, east) for i, a in enumerate(region) for b in region[i + 1 :]
    ]
    # Bridges join the closest rows first (West 1 - East 1, West 2 - East 2, ...), then the others.
    pairs = sorted(
        ((w, e) for w in range(n) for e in range(n)), key=lambda p: (abs(p[0] - p[1]), p)
    )
    crossings = [(west[w], east[e]) for w, e in pairs[:bridges]]
    towns = [*west, *east]
    homes = place_merchants_two_regions(west, east, crossings, merchants)
    place_people(towns, layout, occupations, others_in=homes)
    return world_tables(towns, inside + crossings, layout)


def place_merchants_two_regions(
    west: list[Town], east: list[Town], crossings: list[tuple[Town, Town]], rule: str
) -> list[Town]:
    """The towns merchants live in (they are shared out evenly among them).

    This choice decides what "bridges" can do. Merchants reach their own town and its
    neighbours, so merchants living at the ends of a bridge can trade across it; merchants spread
    over every town mostly broker inside their region, and cross-region trade then depends on
    how many of them happen to sit on a bridge.

    "bridge_towns": the towns at the ends of the bridges, West ends first. Note that this moves
    merchants as bridges are added (1 bridge: two towns with two merchants each; more: one in
    every town), so a sweep over bridges also changes where merchants live.
    "every_town": spread over all towns, whatever the bridges; a bridge sweep then changes roads
    only.
    """
    if rule == "every_town":
        return [*west, *east]
    ends: list[Town] = []
    for w, e in crossings:
        for town in (w, e):
            if town not in ends:
                ends.append(town)
    return sorted(ends, key=lambda t: t in east)  # West before East, keeping bridge order


def villages(
    layout: "LayoutSpec", occupations: dict[str, Any], villages: int, links: str
) -> dict[str, Any]:
    """`villages` small villages, each with one site (kinds spread out along the line), joined
    only to their neighbours: in a line (links = "chain") or a loop ("ring"). Merchants live in
    evenly spaced villages."""
    if villages < 2:
        raise GeneratorError("villages: needs at least 2 villages")
    if links not in ("chain", "ring"):
        raise GeneratorError('villages: links must be "chain" or "ring"')
    if links == "ring":
        places = [
            (0.5 + 0.4 * math.cos(-math.pi / 2 + 2 * math.pi * i / villages),
             0.5 + 0.4 * math.sin(-math.pi / 2 + 2 * math.pi * i / villages))
            for i in range(villages)
        ]  # fmt: skip
    else:
        places = [
            (0.06 + 0.88 * i / (villages - 1), 0.4 if i % 2 == 0 else 0.6) for i in range(villages)
        ]
    towns = [Town(TOWN_NAMES[i], places[i]) for i in range(villages)]
    for town, kind in zip(towns, _interleave(layout.site_capacity, villages), strict=True):
        town.site_kinds.append(kind)

    merchants = sum(n for o, n in layout.population.items() if not occupations[o]["works_at"])
    homes = [int((j + 0.5) * villages / max(1, merchants)) for j in range(merchants)]
    roads = [(towns[i], towns[i + 1]) for i in range(villages - 1)]
    if links == "ring" and villages > 2:
        roads.append((towns[-1], towns[0]))
    place_people(towns, layout, occupations, others_in=[towns[i] for i in homes])
    return world_tables(towns, roads, layout)


GENERATORS = {
    "hub_and_spokes": (hub_and_spokes, {"spokes": int}),
    "two_regions": (
        two_regions,
        {"towns_per_region": int, "bridges": int, "resources": str, "merchants": str},
    ),
    "villages": (villages, {"villages": int, "links": str}),
}


def build(
    params: dict[str, Any], layout: "LayoutSpec", occupations: dict[str, Any]
) -> dict[str, Any]:
    """The [world] towns and roads for a scenario's [generator] table (strictly checked)."""
    name = params.get("name")
    if name not in GENERATORS:
        raise GeneratorError(f"generator.name: must be one of {list(GENERATORS)}, got {name!r}")
    function, expected = GENERATORS[name]
    given = {k: v for k, v in params.items() if k != "name"}
    if set(given) != set(expected):
        raise GeneratorError(f"generator {name!r} takes {sorted(expected)}, got {sorted(given)}")
    for key, kind in expected.items():
        if not isinstance(given[key], kind) or isinstance(given[key], bool):
            raise GeneratorError(f"generator.{key}: expected {kind.__name__}, got {given[key]!r}")
    for occupation in layout.population:
        if occupation not in occupations:
            raise GeneratorError(f"layout.population: no occupation {occupation!r}")
        works_at = occupations[occupation]["works_at"]
        if works_at and works_at not in layout.site_capacity:
            raise GeneratorError(
                f"layout.site_capacity: {occupation}s work at {works_at!r}, which has none"
            )
    return function(layout, occupations, **given)


# --- Shared helpers ---------------------------------------------------------------------------


def split(total: int, weights: list[float]) -> list[int]:
    """`total` whole people shared in proportion to `weights`: rounded down, then the rest go to
    the largest remainders (earlier entries win ties). Deterministic, and sums to `total`."""
    exact = [total * w / sum(weights) for w in weights]
    counts = [int(x) for x in exact]
    by_remainder = sorted(range(len(weights)), key=lambda i: (-(exact[i] - counts[i]), i))
    for i in by_remainder[: total - sum(counts)]:
        counts[i] += 1
    return counts


def place_people(
    towns: list[Town], layout: "LayoutSpec", occupations: dict[str, Any], others_in: list[Town]
) -> None:
    """Producers are shared evenly among the towns with their kind of site (every site of a kind
    is the same size); everyone who works at no site (merchants) is shared evenly among
    `others_in` (a town listed twice gets a double share)."""
    for occupation, total in layout.population.items():
        kind = occupations[occupation]["works_at"]
        homes = [t for t in towns if kind in t.site_kinds] if kind else others_in
        if not homes:
            if total:
                raise GeneratorError(f"no town for the {total} {occupation}s")
            continue
        for town, count in zip(homes, split(total, [1.0] * len(homes)), strict=True):
            if count:
                town.founding[occupation] = town.founding.get(occupation, 0) + count


def world_tables(
    towns: list[Town], roads: list[tuple[Town, Town]], layout: "LayoutSpec"
) -> dict[str, Any]:
    """The drafted towns and roads as [world] tables. Each kind's total capacity is shared
    equally among its sites (scale), so it matches [layout] however many sites there are."""
    sites_of = {kind: sum(kind in t.site_kinds for t in towns) for kind in layout.site_capacity}
    scale = {kind: layout.site_capacity[kind] / count for kind, count in sites_of.items() if count}
    return {
        "towns": {
            t.name: {
                "position": [round(t.position[0], 4), round(t.position[1], 4)],
                "sites": [
                    {"name": f"{t.name} {kind.title()}", "kind": kind, "scale": scale[kind]}
                    for kind in t.site_kinds
                ],
                "founding": dict(t.founding),
            }
            for t in towns
        },
        "roads": [{"from": a.name, "to": b.name, "cost": 1.0} for a, b in roads],
    }


def _spread_kinds(region: list[Town], kinds: list[str]) -> None:
    """Every town in the region gets a site, and every kind appears: kinds go round the towns."""
    for i in range(max(len(region), len(kinds))):
        town, kind = region[i % len(region)], kinds[i % len(kinds)]
        if kind not in town.site_kinds:
            town.site_kinds.append(kind)


def _interleave(capacity: dict[str, float], slots: int) -> list[str]:
    """`slots` site kinds, each kind's share in proportion to its capacity, spread out evenly
    (e.g. farm, mine, farm, mine rather than farm, farm, mine, mine)."""
    counts = split(slots, list(capacity.values()))
    marks = [((j + 0.5) / count, i) for i, count in enumerate(counts) for j in range(count)]
    kinds = list(capacity)
    return [kinds[i] for _, i in sorted(marks)]
