import pytest

from graphsim.config import load_scenario
from graphsim.metrics import normalized_mutual_information
from graphsim.world_gen import build_world


def test_identical_groupings_score_one_whatever_the_names():
    assert normalized_mutual_information([1, 1, 2, 2], ["x", "x", "y", "y"]) == pytest.approx(1.0)


def test_unrelated_groupings_score_zero():
    assert normalized_mutual_information([1, 1, 2, 2], ["x", "y", "x", "y"]) == pytest.approx(0.0)


def test_partial_agreement_is_in_between():
    score = normalized_mutual_information([1, 1, 1, 2, 2, 2], ["x", "x", "y", "y", "y", "y"])
    assert 0.0 < score < 1.0


def test_equal_population_variant_replaces_merchants_one_for_one():
    scenario = load_scenario()
    base = build_world(scenario.config(), seed=1)
    equal = build_world(scenario.config("no_merchants_equal_population"), seed=1)
    assert len(equal.agents) == len(base.agents)
    assert not any(a.occupation == "merchant" for a in equal.agents.values())
