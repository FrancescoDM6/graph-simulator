"""Scenarios: written-out and generated worlds, and the totals every world is held to."""

import pytest

from graphsim import engine
from graphsim.config import ScenarioError, load_scenario
from graphsim.generators import split
from graphsim.world_gen import build_world

# Worlds that differ from three_towns in shape only. merchant_economy changes the mix of
# occupations on purpose, and is checked separately.
SAME_TOTALS = [
    "three_towns",
    "hub_and_spokes",
    "two_regions",
    "isolated_villages",
    "resource_imbalance",
]


def totals(cfg):
    people: dict[str, int] = {}
    capacity: dict[str, float] = {}
    for town in cfg.world.towns.values():
        for occupation, n in town.founding.items():
            people[occupation] = people.get(occupation, 0) + n
        for site in town.sites:
            capacity[site.kind] = capacity.get(site.kind, 0.0) + site.scale
    return people, {kind: round(total, 9) for kind, total in capacity.items()}


def test_every_world_has_the_same_people_and_site_capacity():
    scenario = load_scenario()
    layout = scenario.raw["layout"]
    for name in SAME_TOTALS:
        people, capacity = totals(scenario.config(scenario=name))
        assert people == layout["population"], name
        assert capacity == layout["site_capacity"], name

    people, capacity = totals(scenario.config(scenario="merchant_economy"))
    assert people == {"farmer": 17, "miner": 8, "merchant": 8}  # 4 farmers became merchants
    assert capacity == layout["site_capacity"]


def test_generated_maps_depend_only_on_their_parameters():
    first, second = load_scenario(), load_scenario()
    for name in first.scenarios:
        assert (
            first.config(scenario=name).config_hash() == second.config(scenario=name).config_hash()
        )
    assert (
        first.config(scenario="two_regions").config_hash()
        != first.config(scenario="resource_imbalance").config_hash()
    )


def test_bridges_join_the_regions_and_nothing_else_changes():
    scenario = load_scenario()
    for bridges in (1, 2, 3, 4):
        cfg = scenario.config(scenario="two_regions", overrides={"generator.bridges": bridges})
        west = {t for t, spec in cfg.world.towns.items() if spec.position[0] < 0.5}
        crossing = [r for r in cfg.world.roads if (r.from_ in west) != (r.to in west)]
        assert len(crossing) == bridges
        assert len(cfg.world.roads) == 2 + bridges  # one road inside each two-town region
        assert totals(cfg) == totals(scenario.config(scenario="two_regions"))


def test_merchants_live_at_the_bridges_or_in_every_town():
    scenario = load_scenario()

    def merchant_towns(bridges, rule):
        cfg = scenario.config(
            scenario="two_regions",
            overrides={"generator.bridges": bridges, "generator.merchants": rule},
        )
        return {
            t: s.founding["merchant"]
            for t, s in cfg.world.towns.items()
            if "merchant" in s.founding
        }

    assert sorted(merchant_towns(1, "bridge_towns").values()) == [2, 2]  # two bridge ends
    assert sorted(merchant_towns(3, "bridge_towns").values()) == [1, 1, 1, 1]
    for bridges in (1, 3):
        assert sorted(merchant_towns(bridges, "every_town").values()) == [1, 1, 1, 1]
    assert list(merchant_towns(1, "one_side").values()) == [4]  # all at the West end


def test_split_resources_put_every_farm_in_the_west():
    cfg = load_scenario().config(scenario="resource_imbalance")
    for spec in cfg.world.towns.values():
        kinds = {site.kind for site in spec.sites}
        assert kinds == ({"farm"} if spec.position[0] < 0.5 else {"mine"})


def test_generator_settings_are_checked():
    scenario = load_scenario()
    with pytest.raises(ScenarioError, match="two_regions.toml: two_regions: bridges"):
        scenario.config(scenario="two_regions", overrides={"generator.bridges": 9})
    with pytest.raises(ScenarioError, match="no generator"):
        scenario.config(scenario="three_towns", overrides={"generator.bridges": 2})
    with pytest.raises(ScenarioError, match="not a key"):
        scenario.config(scenario="two_regions", overrides={"generator.bridge": 2})
    with pytest.raises(ScenarioError, match="unknown scenario"):
        scenario.config(scenario="atlantis")


def test_a_site_scale_shrinks_capacity_and_regrowth():
    cfg = load_scenario().config(scenario="isolated_villages")
    world = build_world(cfg, seed=1)
    farm = cfg.site_kinds["farm"]
    farms = [s for s in world.sites.values() if s.kind == "farm"]
    assert len(farms) == 4
    for site in farms:
        assert site.capacity == pytest.approx(farm.capacity / 2)
        assert site.regen == pytest.approx(farm.regen / 2)


def test_split_shares_whole_people_evenly():
    assert split(21, [1, 1]) == [11, 10]
    assert split(4, [1, 1, 1]) == [2, 1, 1]
    assert split(7, [2, 1]) == [5, 2]
    assert sum(split(33, [0.3, 0.3, 0.4])) == 33


def test_every_world_runs():
    scenario = load_scenario()
    for name in scenario.scenarios:
        world = build_world(scenario.config(scenario=name), seed=2)
        for _ in range(30):
            engine.step(world)
        assert world.metrics.history[-1]["population"] > 0, name
