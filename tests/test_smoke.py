"""Phase 1 smoke test: every module imports, version is readable, config loads."""

from __future__ import annotations

import importlib

import pytest

MODULES = [
    "ie_ur5e",
    "ie_ur5e.connection",
    "ie_ur5e.dashboard",
    "ie_ur5e.motion",
    "ie_ur5e.safety",
    "ie_ur5e.api",
    "ie_ur5e.cli",
]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports(mod: str) -> None:
    importlib.import_module(mod)


def test_version_is_readable() -> None:
    import ie_ur5e

    assert isinstance(ie_ur5e.__version__, str)
    assert ie_ur5e.__version__.count(".") >= 1


def test_config_loads_with_defaults() -> None:
    from ie_ur5e.connection import load_config

    cfg = load_config()
    assert cfg.host_ip
    assert cfg.rtde_frequency == 125
    assert len(cfg.tcp_offset) == 6
    assert len(cfg.home_joints_rad) == 6
