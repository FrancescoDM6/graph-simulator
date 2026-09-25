"""Every tunable number in the simulation, in one place.

Change values here (or pass a modified copy via `dataclasses.replace`) to tune behaviour.
Units: goods are measured in "rations"/"lumps", time in ticks, trust and strength are 0..1.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SimConfig:
    # --- Population (the founding mix of each town is in world_gen.TOWNS) --------------------
    arrival_chance: float = 0.10  # chance per tick that a newcomer fills an empty job
    start_food: float = 8.0
    start_ore: float = 3.0
    start_coin: float = 15.0
    initial_ties_per_agent: int = 2  # random acquaintances in the same town at tick 0

    # --- Eating and starving -----------------------------------------------------------------
    food_per_tick: float = 1.0
    food_spoil_rate: float = 0.03  # fraction of held food lost each tick
    starving_notice_after: int = 3  # hungry ticks before a "starving" event is logged
    leave_after_hungry: int = 12  # hungry ticks before the agent leaves the world

    # --- Production --------------------------------------------------------------------------
    farm_yield: float = 3.0  # food per farmer per tick, with tools
    farm_yield_no_tools: float = 2.0  # food per farmer per tick, without ore
    ore_per_harvest: float = 0.5  # ore a farmer uses up per harvest
    mine_yield: float = 1.5  # ore per miner per tick
    farm_capacity: float = 80.0
    farm_regen: float = 26.0
    mine_capacity: float = 60.0
    mine_regen: float = 10.0
    max_holding: float = 40.0  # producers stop harvesting once they hold this much
    drought_every: int = 200  # ticks between drought starts
    drought_length: int = 60
    drought_regen_factor: float = 0.4  # farm regen multiplier during a drought

    # --- Needs -------------------------------------------------------------------------------
    food_reserve: float = 4.0  # below this an agent wants food; above it food is "spare"
    food_buy_target: float = 8.0  # how much food a buyer tries to hold after buying
    ore_reserve: float = 1.0  # farmers want ore below this
    ore_buy_target: float = 3.0  # how much ore a farmer tries to hold after buying

    # --- Prices ------------------------------------------------------------------------------
    start_price_food: float = 1.0
    start_price_ore: float = 1.5
    price_adjust_rate: float = 0.02  # max fractional price change per tick
    min_price: float = 0.1
    max_price: float = 10.0
    price_event_change: float = 0.25  # log a price event after a 25% move since the last one
    town_levy: float = 0.01  # share of coin each resident pays per tick, split among residents

    # --- Trade -------------------------------------------------------------------------------
    merchant_markup: float = 0.5  # a broker's commission, as a fraction of the price
    brokered_weight: float = 0.5  # buyers favour direct deals over going through a broker
    trust_discount: float = 0.2  # a fully trusted partner gets this fraction off
    max_trade_attempts: int = 3  # suppliers tried per need per tick
    stranger_weight: float = 0.3  # partner-choice weight for someone with no social tie
    gift_min_strength: float = 0.6  # tie strength needed before a friend gives food away
    gift_amount: float = 2.0

    # --- Relationships -----------------------------------------------------------------------
    initial_trust: float = 0.4
    trust_gain: float = 0.08  # on success, trust moves this fraction of the way to 1
    trust_loss: float = 0.1  # when an acquaintance refuses to help, trust drops by this much
    trusted_above: float = 0.7  # crossing this logs "became trusted"
    distrusted_below: float = 0.25  # crossing this logs "lost trust"
    social_bump: float = 0.1  # social strength gained per interaction
    trade_bump: float = 0.2  # trade strength gained per successful trade
    socialize_bump: float = 0.05  # strength gained when an agent spends a tick with a friend
    social_decay: float = 0.01  # fraction of social strength lost per idle tick
    trade_decay: float = 0.04
    trade_friendship_at: float = 0.5  # trade-tie strength at which partners form a social tie
    prune_below: float = 0.05  # ties weaker than this disappear
    max_social_ties: int = 7  # attention limit
    meet_chance: float = 0.02  # per agent per tick
    meet_strength: float = 0.25
    intro_chance: float = 0.02  # per agent per tick
    intro_min_strength: float = 0.5  # only close friends make introductions

    # --- Organizations -----------------------------------------------------------------------
    join_score: float = 1.2  # summed trust in an org's members needed to join it
    leave_below_trust: float = 0.35  # average trust in fellow members needed to stay
    found_chance: float = 0.02
    found_min_friends: int = 3
    found_min_trust: float = 0.6
    max_orgs: int = 6

    # --- Metrics and structural events -------------------------------------------------------
    min_component_size: int = 3  # smaller connected groups (e.g. a lone newcomer) aren't counted
    min_community_size: int = 4
    community_match_jaccard: float = 0.3  # overlap needed to keep a community's label
    gini_window: int = 50
    gini_jump: float = 0.08
