import copy

import pytest

from graphsim import engine
from graphsim.config import (
    DEFAULT_SCENARIO,
    Scenario,
    ScenarioError,
    load_scenario,
    parse_override,
    parse_seeds,
)
from graphsim.world_gen import build_world


def scenario_with(change, change_worlds=None) -> Scenario:
    """The default scenario with its parsed TOML edited by `change(raw)`, and its scenario files
    (scenarios/*.toml, by name) by `change_worlds(files)`."""
    loaded = load_scenario()
    raw, files = copy.deepcopy(loaded.raw), copy.deepcopy(loaded.scenario_files)
    change(raw)
    if change_worlds:
        change_worlds(files)
    return Scenario(raw, DEFAULT_SCENARIO, files)


def test_default_scenario_and_all_variants_load():
    scenario = load_scenario()
    for variant in scenario.variants:
        scenario.config(variant)
    assert scenario.config("no_gifting").mechanisms.gifting is False
    assert scenario.config().mechanisms.gifting is True


def test_unknown_key_is_an_error_naming_its_place():
    with pytest.raises(ScenarioError, match="trade: unknown key"):
        scenario_with(lambda raw: raw["trade"].update(broker_comission=0.5))  # typo


def test_missing_key_is_an_error():
    with pytest.raises(ScenarioError, match="missing key"):
        scenario_with(lambda raw: raw["trade"].pop("gift_amount"))


def test_wrong_type_is_an_error():
    with pytest.raises(ScenarioError, match="max_attempts"):
        scenario_with(lambda raw: raw["trade"].update(max_attempts="three"))


def test_broken_reference_is_an_error():
    with pytest.raises(ScenarioError, match="no good called 'wood'"):
        scenario_with(lambda raw: raw["occupations"]["farmer"].update(tool="wood"))


def test_overrides_and_variants_change_only_what_they_name():
    scenario = load_scenario()
    base = scenario.config()
    changed = scenario.config(overrides={"trade.broker_commission": 0.9})
    assert changed.trade.broker_commission == 0.9
    assert changed.relationships == base.relationships
    assert changed.config_hash() != base.config_hash()
    assert scenario.config().config_hash() == base.config_hash()
    with pytest.raises(ScenarioError):
        scenario.config(overrides={"trade.no_such_key": 1})


def test_parsing_helpers():
    assert parse_override("trade.broker_commission=0.8") == ("trade.broker_commission", 0.8)
    assert parse_override("mechanisms.partner_choice=random_global") == (
        "mechanisms.partner_choice",
        "random_global",
    )
    assert parse_seeds("1-3,7") == [1, 2, 3, 7]


def test_a_new_good_site_and_occupation_need_no_code():
    def add_forestry(raw):
        raw["goods"]["wood"] = dict(raw["goods"]["ore"], start_amount=0.0)
        raw["site_kinds"]["forest"] = {
            "produces": "wood",
            "capacity": 50.0,
            "regen": 5.0,
            "drought_sensitive": True,
        }
        raw["occupations"]["woodcutter"] = dict(raw["occupations"]["miner"], works_at="forest")

    def add_wood_to_ashford(worlds):
        ashford = worlds["three_towns"]["world"]["towns"]["Ashford"]
        ashford["sites"].append({"name": "Old Wood", "kind": "forest", "scale": 1.0})
        ashford["founding"]["woodcutter"] = 3

    cfg = scenario_with(add_forestry, add_wood_to_ashford).config()
    world = build_world(cfg, seed=1)
    for _ in range(20):
        engine.step(world)

    assert cfg.producers_of("wood") == ["woodcutter"]
    assert world.metrics.history[-1]["stock.wood"] > 0
    assert world.metrics.history[-1]["population.woodcutter"] == 3
