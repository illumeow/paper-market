import os
import tomllib
from dataclasses import dataclass, field
from app.domain.price_engine import Tuning


@dataclass
class Config:
    economy: dict
    tuning: Tuning
    tick_seconds: float
    quarter_min: float
    event_duration_min: float
    stocks: list = field(default_factory=list)
    events: list = field(default_factory=list)
    staff_password: str = ""
    secret_key: str = ""


def load_config(path="config/config.toml") -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    t = raw["tuning"]
    tuning = Tuning(beta=t["beta"], depth=t["depth"], mu=t["mu"],
                    net_flow_decay=t["net_flow_decay"], gamma=t["gamma"], sigma=t["sigma"])
    return Config(
        economy=raw["economy"],
        tuning=tuning,
        tick_seconds=t["tick_seconds"],
        quarter_min=raw["economy"]["quarter_min"],
        event_duration_min=raw["economy"]["event_duration_min"],
        stocks=raw.get("stocks", []),
        events=raw.get("events", []),
        staff_password=os.environ.get("STAFF_PASSWORD", "dev-staff"),
        secret_key=os.environ.get("SECRET_KEY", "dev-secret"),
    )
