"""The shape of scenario.toml, and the code that reads it.

The values live only in scenario.toml; the dataclasses here define which keys must exist and
what type each one has. Loading is strict: a missing key, an unknown key, or a value of the
wrong type stops with an error naming the exact place, so a typo can never silently change an
experiment.

    scenario = load_scenario()                         # the file, parsed
    cfg = scenario.config("no_gifting")                # SimConfig for one variant
    cfg = scenario.config(overrides={"trade.broker_commission": 0.8})

Only SimConfig reaches the simulation (as `world.cfg`). Its hash identifies a run's settings.
"""

import copy
import dataclasses
import hashlib
import json
import tomllib
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = REPO_ROOT / "scenario.toml"


class ScenarioError(ValueError):
    """scenario.toml (or a variant/override) is missing a key, has an extra one, or a bad value."""


# --- Economy ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class GoodSpec:
    eaten_per_tick: float
    spoil_rate: float
    start_amount: float
    reserve: float
    buy_target: float
    start_price: float
    max_holding: float


@dataclass(frozen=True)
class SiteKindSpec:
    produces: str
    capacity: float
    regen: float
    drought_sensitive: bool


@dataclass(frozen=True)
class OccupationSpec:
    works_at: str  # site kind, or "" for none
    output: float
    tool: str  # good, or "" for none
    tool_use: float
    output_without_tool: float
    brokers: bool
    reach: str  # "home" or "home_and_neighbours"
    color: str


# --- World ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteSpec:
    name: str
    kind: str


@dataclass(frozen=True)
class TownSpec:
    sites: tuple[SiteSpec, ...]
    founding: dict[str, int]  # occupation -> count; order is the order agents are created in


@dataclass(frozen=True)
class RoadSpec:
    from_: str  # "from" in the file
    to: str
    cost: float


@dataclass(frozen=True)
class WorldSpec:
    site_access_cost: float
    names: tuple[str, ...]
    towns: dict[str, TownSpec]
    roads: tuple[RoadSpec, ...]


# --- Behaviour --------------------------------------------------------------------------------


@dataclass(frozen=True)
class PopulationSpec:
    arrival_chance: float
    start_coin: float
    initial_ties_per_agent: int
    starving_notice_after: int
    leave_after_hungry: int


@dataclass(frozen=True)
class PricesSpec:
    adjust_rate: float
    min: float
    max: float
    event_change: float
    town_levy: float


@dataclass(frozen=True)
class TradeSpec:
    broker_commission: float
    brokered_weight: float
    trust_discount: float
    max_attempts: int
    stranger_weight: float
    min_amount: float
    gift_min_strength: float
    gift_amount: float
    help_keeps_ticks: int


@dataclass(frozen=True)
class RelationshipsSpec:
    initial_trust: float
    trust_gain: float
    trust_loss: float
    trusted_above: float
    distrusted_below: float
    social_bump: float
    trade_bump: float
    socialize_bump: float
    social_decay: float
    trade_decay: float
    trade_friendship_at: float
    prune_below: float
    max_social_ties: int
    meet_chance: float
    meet_strength: float
    intro_chance: float
    intro_min_strength: float


@dataclass(frozen=True)
class OrganizationsSpec:
    join_score: float
    leave_below_trust: float
    found_chance: float
    found_min_friends: int
    found_min_trust: float
    max_orgs: int
    name_words: tuple[str, ...]


@dataclass(frozen=True)
class SeasonsSpec:
    drought_every: int
    drought_length: int
    drought_regen_factor: float


@dataclass(frozen=True)
class MetricsSpec:
    min_component_size: int
    min_community_size: int
    community_match_jaccard: float
    community_min_lifespan: int
    gini_window: int
    gini_jump: float
    broker_overtake_margin: float
    min_broker_betweenness: float


SOCIAL_DYNAMICS = ("dynamic", "frozen_topology", "frozen")
PARTNER_CHOICE = ("network", "random_reachable", "random_global")


@dataclass(frozen=True)
class Mechanisms:
    gifting: bool
    brokering: bool
    meetings: bool
    introductions: bool
    trade_friendships: bool
    organizations: bool
    droughts: bool
    price_adjustment: bool
    town_levy: bool
    attention_limit: bool
    social_dynamics: str  # one of SOCIAL_DYNAMICS
    partner_choice: str  # one of PARTNER_CHOICE


# --- Everything the simulation reads ----------------------------------------------------------


@dataclass(frozen=True)
class SimConfig:
    goods: dict[str, GoodSpec]
    site_kinds: dict[str, SiteKindSpec]
    occupations: dict[str, OccupationSpec]
    world: WorldSpec
    population: PopulationSpec
    prices: PricesSpec
    trade: TradeSpec
    relationships: RelationshipsSpec
    organizations: OrganizationsSpec
    seasons: SeasonsSpec
    metrics: MetricsSpec
    mechanisms: Mechanisms

    # --- questions the rules ask about the economy ---

    def eaten_goods(self) -> list[str]:
        return [g for g, spec in self.goods.items() if spec.eaten_per_tick > 0]

    def produced_by(self, occupation: str) -> str:
        """The good an occupation produces, or "" if it produces nothing."""
        site_kind = self.occupations[occupation].works_at
        return self.site_kinds[site_kind].produces if site_kind else ""

    def producers_of(self, good: str) -> list[str]:
        """Occupations that produce a good (and so sell it)."""
        return [o for o in self.occupations if self.produced_by(o) == good]

    def needs_good(self, occupation: str, good: str) -> bool:
        """Whether an agent of this occupation keeps a reserve of the good (to eat or as a tool)."""
        return self.goods[good].eaten_per_tick > 0 or self.occupations[occupation].tool == good

    def is_broker(self, occupation: str) -> bool:
        return self.occupations[occupation].brokers and self.mechanisms.brokering

    def config_hash(self) -> str:
        """Identifies these exact settings (used to find cached runs)."""
        text = json.dumps(dataclasses.asdict(self), sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:16]


SIM_SECTIONS = [f.name for f in dataclasses.fields(SimConfig)]


# --- Project-level sections (not part of the simulation itself) ------------------------------


@dataclass(frozen=True)
class ExperimentSpec:
    description: str
    seeds: list[int]
    ticks: int
    level: str
    variants: list[str]
    sweep: dict[str, list[Any]]


@dataclass(frozen=True)
class PhenomenonSpec:
    description: str
    measure: str
    present_if: str  # e.g. ">= 2.0"

    def is_present(self, value: float) -> bool:
        operator, threshold_text = self.present_if.split()
        threshold = float(threshold_text)
        if operator == ">=":
            return value >= threshold
        if operator == ">":
            return value > threshold
        if operator == "<=":
            return value <= threshold
        if operator == "<":
            return value < threshold
        raise ScenarioError(f"present_if {self.present_if!r}: use >=, >, <= or <")


@dataclass(frozen=True)
class RecordingSpec:
    metrics_every: int
    agent_history_every: int  # 0 = never
    detail_events: bool
    trust_ledger: bool
    snapshots: bool


class Scenario:
    """scenario.toml, parsed. Use `config()` to get the SimConfig for a variant."""

    def __init__(self, raw: dict[str, Any], path: Path) -> None:
        self.raw = raw
        self.path = path
        self.name = path.stem
        self.seed: int = _require(raw, "run", "seed")
        self.ticks: int = _require(raw, "run", "ticks")
        self.database = (path.parent / _require(raw, "run", "database")).resolve()
        self.variants: dict[str, dict[str, Any]] = raw.get("variants", {})
        self.experiments = {
            name: _build(ExperimentSpec, _with_seed_list(spec), f"experiments.{name}")
            for name, spec in raw.get("experiments", {}).items()
        }
        self.phenomena = {
            name: _build(PhenomenonSpec, spec, f"phenomena.{name}")
            for name, spec in raw.get("phenomena", {}).items()
        }
        self.recording = {
            level: _build(RecordingSpec, spec, f"recording.{level}")
            for level, spec in _require(raw, "recording").items()
        }
        self.viewer: dict[str, Any] = raw.get("viewer", {})
        # Validate everything now, not at first use.
        for name in self.variants:
            self.config(name)
        for name, experiment in self.experiments.items():
            for variant in experiment.variants:
                if variant not in self.variants:
                    raise ScenarioError(f"experiments.{name}: unknown variant {variant!r}")
            if experiment.level not in self.recording:
                raise ScenarioError(f"experiments.{name}.level: no [recording.{experiment.level}]")

    def config(
        self, variant: str | None = None, overrides: dict[str, Any] | None = None
    ) -> SimConfig:
        sim_raw = {section: copy.deepcopy(self.raw.get(section)) for section in SIM_SECTIONS}
        if variant and variant != "baseline":
            if variant not in self.variants:
                raise ScenarioError(f"unknown variant {variant!r}; known: {list(self.variants)}")
            changes = {k: v for k, v in self.variants[variant].items() if k != "description"}
            _deep_merge(sim_raw, changes, f"variants.{variant}")
        for dotted_key, value in (overrides or {}).items():
            _set_dotted(sim_raw, dotted_key, value)
        cfg = _build(SimConfig, sim_raw, "")
        _check_references(cfg)
        return cfg


def load_scenario(path: Path | str = DEFAULT_SCENARIO) -> Scenario:
    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return Scenario(raw, path)


def parse_override(text: str) -> tuple[str, Any]:
    """'trade.broker_commission=0.8' -> ('trade.broker_commission', 0.8). Values use TOML syntax;
    anything that isn't valid TOML is taken as a plain string."""
    key, _, value_text = text.partition("=")
    try:
        value = tomllib.loads(f"v = {value_text.strip()}")["v"]
    except tomllib.TOMLDecodeError:
        value = value_text.strip()
    return key.strip(), value


def parse_seeds(spec: str | list[int]) -> list[int]:
    """'1-100' -> [1..100]; '1,4,7' -> [1, 4, 7]; a list is returned as is."""
    if isinstance(spec, list):
        return spec
    seeds: list[int] = []
    for part in str(spec).split(","):
        if "-" in part:
            start, end = part.split("-")
            seeds.extend(range(int(start), int(end) + 1))
        else:
            seeds.append(int(part))
    return seeds


# --- strict dict -> dataclass building --------------------------------------------------------


def _build(cls: type, data: Any, path: str) -> Any:
    """Builds a (nested) dataclass from parsed TOML, failing on missing/unknown keys or types."""
    where = path or "scenario"
    if not isinstance(data, dict):
        raise ScenarioError(f"{where}: expected a table, got {data!r}")
    hints = typing.get_type_hints(cls)
    file_keys = {_file_key(f.name): f.name for f in dataclasses.fields(cls)}
    unknown = sorted(set(data) - set(file_keys))
    missing = sorted(key for key in file_keys if key not in data)
    if unknown:
        raise ScenarioError(f"{where}: unknown key(s) {unknown}")
    if missing:
        raise ScenarioError(f"{where}: missing key(s) {missing}")
    values = {
        name: _convert(hints[name], data[key], f"{path}.{key}".lstrip("."))
        for key, name in file_keys.items()
    }
    return cls(**values)


def _convert(hint: Any, value: Any, path: str) -> Any:
    origin = typing.get_origin(hint)
    if dataclasses.is_dataclass(hint):
        return _build(hint, value, path)
    if hint is Any:
        return value
    if origin is dict:
        _, value_type = typing.get_args(hint)
        if not isinstance(value, dict):
            raise ScenarioError(f"{path}: expected a table")
        return {k: _convert(value_type, v, f"{path}.{k}") for k, v in value.items()}
    if origin in (tuple, list):
        item_type = typing.get_args(hint)[0]
        if not isinstance(value, list):
            raise ScenarioError(f"{path}: expected a list")
        items = [_convert(item_type, v, f"{path}[{i}]") for i, v in enumerate(value)]
        return tuple(items) if origin is tuple else items
    if hint is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, hint) or (hint is not bool and isinstance(value, bool)):
        raise ScenarioError(f"{path}: expected {hint.__name__}, got {value!r}")
    return value


def _file_key(field_name: str) -> str:
    """Python names that are keywords get a trailing underscore: `from_` is "from" in the file."""
    return field_name.rstrip("_")


def _deep_merge(base: dict[str, Any], changes: dict[str, Any], path: str) -> None:
    """Merges a variant into the scenario. Nested tables merge key by key, so a variant only
    lists what it changes; new keys are allowed below the top level (e.g. a new town), and
    building the dataclasses afterwards still rejects anything that isn't a real setting."""
    for key, value in changes.items():
        if key not in base and path.count(".") <= 1:
            raise ScenarioError(f"{path}.{key}: not a section of the scenario")
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value, f"{path}.{key}")
        else:
            base[key] = copy.deepcopy(value)


def _set_dotted(raw: dict[str, Any], dotted_key: str, value: Any) -> None:
    *parents, last = dotted_key.split(".")
    node = raw
    for part in parents:
        if not isinstance(node.get(part), dict):
            raise ScenarioError(f"override {dotted_key!r}: {part!r} is not a table")
        node = node[part]
    if last not in node:
        raise ScenarioError(f"override {dotted_key!r}: {last!r} is not a key")
    node[last] = value


def _require(raw: dict[str, Any], *keys: str) -> Any:
    node: Any = raw
    for i, key in enumerate(keys):
        if not isinstance(node, dict) or key not in node:
            raise ScenarioError(f"missing key {'.'.join(keys[: i + 1])}")
        node = node[key]
    return node


def _with_seed_list(spec: dict[str, Any]) -> dict[str, Any]:
    return {**spec, "seeds": parse_seeds(spec.get("seeds", []))}


def _check_references(cfg: SimConfig) -> None:
    """Names that point at other sections must exist."""
    for name, kind in cfg.site_kinds.items():
        if kind.produces not in cfg.goods:
            raise ScenarioError(f"site_kinds.{name}.produces: no good called {kind.produces!r}")
    for name, occ in cfg.occupations.items():
        if occ.works_at and occ.works_at not in cfg.site_kinds:
            raise ScenarioError(f"occupations.{name}.works_at: no site kind {occ.works_at!r}")
        if occ.tool and occ.tool not in cfg.goods:
            raise ScenarioError(f"occupations.{name}.tool: no good called {occ.tool!r}")
        if occ.reach not in ("home", "home_and_neighbours"):
            raise ScenarioError(f"occupations.{name}.reach: use 'home' or 'home_and_neighbours'")
    for town_name, town in cfg.world.towns.items():
        for site in town.sites:
            if site.kind not in cfg.site_kinds:
                raise ScenarioError(f"world.towns.{town_name}: no site kind {site.kind!r}")
        for occupation in town.founding:
            if occupation not in cfg.occupations:
                raise ScenarioError(f"world.towns.{town_name}.founding: no {occupation!r}")
    for road in cfg.world.roads:
        for end in (road.from_, road.to):
            if end not in cfg.world.towns:
                raise ScenarioError(f"world.roads: no town called {end!r}")
    if cfg.mechanisms.social_dynamics not in SOCIAL_DYNAMICS:
        raise ScenarioError(f"mechanisms.social_dynamics: must be one of {SOCIAL_DYNAMICS}")
    if cfg.mechanisms.partner_choice not in PARTNER_CHOICE:
        raise ScenarioError(f"mechanisms.partner_choice: must be one of {PARTNER_CHOICE}")
