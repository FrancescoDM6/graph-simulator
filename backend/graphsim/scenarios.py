"""The worlds in scenarios/, side by side: `python -m graphsim.scenarios`.

Prints each world's people by occupation, site capacity by kind, and the shape of its road
map, so that anything besides shape that differs between worlds (a confound) is visible before
an experiment compares them.
"""

import networkx as nx

from graphsim.config import SimConfig, load_scenario


def world_summary(cfg: SimConfig) -> dict[str, float | int | str]:
    """Totals and road-map shape of one world (also served to the viewer)."""
    people: dict[str, int] = {}
    capacity: dict[str, float] = {}
    for town in cfg.world.towns.values():
        for occupation, n in town.founding.items():
            people[occupation] = people.get(occupation, 0) + n
        for site in town.sites:
            capacity[site.kind] = capacity.get(site.kind, 0.0) + site.scale
    roads = nx.Graph()
    roads.add_nodes_from(cfg.world.towns)
    roads.add_edges_from((r.from_, r.to) for r in cfg.world.roads)
    connected = nx.is_connected(roads)
    return {
        "people": sum(people.values()),
        **{f"people.{o}": people.get(o, 0) for o in cfg.occupations},
        **{f"capacity.{k}": round(capacity.get(k, 0.0), 6) for k in cfg.site_kinds},
        "towns": roads.number_of_nodes(),
        "roads": roads.number_of_edges(),
        "mean_road_degree": round(2 * roads.number_of_edges() / max(1, roads.number_of_nodes()), 3),
        "diameter": nx.diameter(roads) if connected else "disconnected",
    }


def main() -> None:
    scenario = load_scenario()
    rows = {name: world_summary(scenario.config(scenario=name)) for name in scenario.scenarios}
    columns = list(next(iter(rows.values())))
    width = max(len(name) for name in rows) + 2
    print("".ljust(width) + "".join(c.split(".")[-1][:10].rjust(11) for c in columns))
    for name, row in rows.items():
        print(name.ljust(width) + "".join(str(row[c]).rjust(11) for c in columns))


if __name__ == "__main__":
    main()
