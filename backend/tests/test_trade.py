from graphsim.model import Layer, Occupation
from graphsim.rules import needs, relationships, trade
from tests.helpers import TOWN, add_agent, add_town, befriend, make_world


def trade_one_tick(world):
    needs.evaluate_needs(world)
    trade.run_trading(world)
    relationships.apply_interactions(world)


def test_hungry_miner_buys_spare_food_from_a_farmer_in_town():
    world = make_world()
    farmer = add_agent(world, Occupation.FARMER, food=20.0, ore=5.0, coin=0.0)
    miner = add_agent(world, Occupation.MINER, food=0.0, coin=10.0)

    trade_one_tick(world)

    assert miner.food > 0
    assert farmer.coin > 0
    assert miner.coin + farmer.coin == 10.0  # coin moves, it isn't created
    assert world.get_edge(miner.id, farmer.id, Layer.TRADE) is not None


def test_merchant_brokers_between_towns_and_takes_a_commission():
    world = make_world()
    farm_town = TOWN
    mine_town = add_town(world, "Minesville", road_to=farm_town)
    farmer = add_agent(world, Occupation.FARMER, food=20.0, ore=5.0, coin=0.0, home=farm_town)
    miner = add_agent(world, Occupation.MINER, food=0.0, coin=10.0, home=mine_town)
    merchant = add_agent(world, Occupation.MERCHANT, food=10.0, coin=0.0, home=mine_town)

    trade_one_tick(world)

    assert miner.food > 0
    assert merchant.coin > 0  # commission
    assert farmer.coin > merchant.coin  # the producer still gets most of the price
    assert world.get_edge(miner.id, merchant.id, Layer.TRADE) is not None
    assert world.get_edge(merchant.id, farmer.id, Layer.TRADE) is not None
    assert world.get_edge(miner.id, farmer.id, Layer.TRADE) is None


def test_close_friend_gives_food_to_a_starving_broke_friend():
    world = make_world()
    farmer = add_agent(world, Occupation.FARMER, food=20.0, ore=5.0, coin=0.0)
    miner = add_agent(world, Occupation.MINER, food=0.0, coin=0.0)
    befriend(world, farmer, miner, strength=0.9, trust=0.5)

    trade_one_tick(world)

    assert miner.food == world.cfg.gift_amount
    assert farmer.coin == 0.0
    assert world.get_edge(farmer.id, miner.id, Layer.SOCIAL).trust > 0.5
    assert any(e.kind == "gift" for e in world.log.events)


def test_acquaintance_who_refuses_to_help_loses_trust():
    world = make_world()
    farmer = add_agent(world, Occupation.FARMER, food=20.0, ore=5.0, coin=0.0)
    miner = add_agent(world, Occupation.MINER, food=0.0, coin=0.0)
    befriend(world, farmer, miner, strength=0.3, trust=0.5)

    trade_one_tick(world)

    assert miner.food == 0.0
    assert [i.outcome for i in world.interactions] == ["refused"]
    assert world.get_edge(farmer.id, miner.id, Layer.SOCIAL).trust < 0.5


def test_seller_with_nothing_to_spare_is_not_blamed():
    world = make_world()
    farmer = add_agent(world, Occupation.FARMER, food=world.cfg.food_reserve, ore=5.0, coin=0.0)
    miner = add_agent(world, Occupation.MINER, food=1.5, coin=10.0)  # hungry soon, not starving
    befriend(world, farmer, miner, strength=0.3, trust=0.5)

    trade_one_tick(world)

    assert [i.outcome for i in world.interactions] == ["no_surplus"]
    assert world.get_edge(farmer.id, miner.id, Layer.SOCIAL).trust == 0.5
