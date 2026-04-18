"""Shared connection helpers — config loading and host resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class RobotConfig:
    host_ip: str
    rtde_frequency: int = 125
    tcp_offset: list[float] = field(default_factory=lambda: [0.0] * 6)
    payload_kg: float = 0.0
    home_joints_rad: list[float] = field(
        default_factory=lambda: [0.0, -1.5708, 0.0, -1.5708, 0.0, 0.0]
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> RobotConfig:
    """Load config/robot.yaml, overlay ROBOT_IP from .env / env."""
    load_dotenv(_project_root() / ".env", override=False)

    cfg_path = Path(path) if path else _project_root() / "config" / "robot.yaml"
    data: dict = {}
    if cfg_path.exists():
        with cfg_path.open() as f:
            data = yaml.safe_load(f) or {}

    host = os.environ.get("ROBOT_IP") or data.get("host_ip") or "127.0.0.1"

    return RobotConfig(
        host_ip=host,
        rtde_frequency=int(data.get("rtde_frequency", 125)),
        tcp_offset=list(data.get("tcp_offset", [0.0] * 6)),
        payload_kg=float(data.get("payload_kg", 0.0)),
        home_joints_rad=list(data.get("home_joints_rad", [0.0, -1.5708, 0.0, -1.5708, 0.0, 0.0])),
    )


def resolve_host(override: str | None = None) -> str:
    if override:
        return override
    load_dotenv(_project_root() / ".env", override=False)
    return os.environ.get("ROBOT_IP") or load_config().host_ip
