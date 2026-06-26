import logging
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
    tuning = Tuning(impact_strength=t["impact_strength"], impact_depth=t["impact_depth"],
                    momentum_strength=t["momentum_strength"], momentum_decay=t["momentum_decay"],
                    reversion_strength=t["reversion_strength"], noise_scale=t["noise_scale"])
    staff_password = os.environ.get("STAFF_PASSWORD") or ""
    secret_key = os.environ.get("SECRET_KEY") or ""
    if not staff_password:
        logging.warning("STAFF_PASSWORD not set — using insecure dev default; set it in production")
        staff_password = "dev-staff"
    if not secret_key:
        logging.warning("SECRET_KEY not set — using insecure dev default; set it in production")
        secret_key = "dev-secret"
    return Config(
        economy=raw["economy"],
        tuning=tuning,
        tick_seconds=t["tick_seconds"],
        quarter_min=raw["economy"]["quarter_min"],
        event_duration_min=raw["economy"]["event_duration_min"],
        stocks=raw.get("stocks", []),
        events=raw.get("events", []),
        staff_password=staff_password,
        secret_key=secret_key,
    )
