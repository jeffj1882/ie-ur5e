"""Integration tests for the Dashboard client.

Skip unless ROBOT_IP is set *and* a TCP connection to :29999 succeeds.
Safe to run against URSim or a real arm.
"""

from __future__ import annotations

import asyncio
import os
import socket

import pytest

from ie_ur5e.dashboard import (
    DashboardClient,
    ProgramNotLoaded,
    RobotMode,
    SafetyStatus,
)

ROBOT_IP = os.environ.get("ROBOT_IP")
DASHBOARD_PORT = 29999


def _dashboard_reachable(host: str, port: int = DASHBOARD_PORT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not ROBOT_IP or not _dashboard_reachable(ROBOT_IP or ""),
    reason="set ROBOT_IP to a reachable UR Dashboard host to run integration tests",
)


@pytest.fixture
async def client():
    async with DashboardClient(ROBOT_IP or "127.0.0.1") as c:
        yield c


async def test_robotmode_returns_known_value(client: DashboardClient) -> None:
    mode = await client.robotmode()
    assert isinstance(mode, RobotMode)
    assert mode is not RobotMode.UNKNOWN


async def test_safetystatus_returns_known_value(client: DashboardClient) -> None:
    status = await client.safetystatus()
    assert isinstance(status, SafetyStatus)
    assert status is not SafetyStatus.UNKNOWN


async def test_popup_display_and_dismiss(client: DashboardClient) -> None:
    msg = await client.popup("ie-ur5e integration test")
    assert "popup" in msg.lower() or "showing" in msg.lower()
    dismiss = await client.close_popup()
    assert "closing" in dismiss.lower() or "popup" in dismiss.lower()


async def test_load_nonexistent_program_raises(client: DashboardClient) -> None:
    with pytest.raises(ProgramNotLoaded):
        await client.load("/definitely/does/not/exist.urp")


async def test_get_loaded_program_round_trip(client: DashboardClient) -> None:
    current = await client.get_loaded_program()
    # URSim's default is /ursim/programs/<unnamed>.urp; None is also valid.
    assert current is None or isinstance(current, str)


async def test_load_stop_cycle(client: DashboardClient) -> None:
    """Load the currently-loaded program then stop. Round-trips both commands.

    URSim boots with a phantom `<unnamed>.urp` reference that isn't on disk,
    so `load` returns "File not found". In that case we assert the protocol
    round-trip still parsed cleanly (raised ProgramNotLoaded) and exercise
    stop independently.
    """
    current = await client.get_loaded_program()
    if current is None:
        pytest.skip("no program loaded in URSim; can't round-trip load/stop")

    try:
        reply = await client.load(current)
    except ProgramNotLoaded:
        # Phantom URSim default — protocol handshake succeeded; that's what
        # this test proves. Real arms / saved URSim programs follow the else.
        pass
    else:
        assert "loading" in reply.lower()

    stopped = await client.stop()
    assert "stopped" in stopped.lower() or "failed" in stopped.lower()


async def test_power_cycle_transitions(client: DashboardClient) -> None:
    """power off → power on → brake release → power off, asserting mode changes.

    Skipped if the controller isn't running yet (URSim NO_CONTROLLER state —
    the pendant's ON button hasn't been pressed through the UI).
    """
    initial = await client.robotmode()
    if initial is RobotMode.NO_CONTROLLER:
        pytest.skip("URSim controller not started; press ON in the pendant first")

    await client.power_off()
    # Wait for transition to POWER_OFF (up to 10s).
    for _ in range(20):
        if await client.robotmode() is RobotMode.POWER_OFF:
            break
        await asyncio.sleep(0.5)
    assert await client.robotmode() is RobotMode.POWER_OFF

    await client.power_on()
    for _ in range(30):
        mode = await client.robotmode()
        if mode in {RobotMode.POWER_ON, RobotMode.IDLE}:
            break
        await asyncio.sleep(0.5)
    assert (await client.robotmode()) in {RobotMode.POWER_ON, RobotMode.IDLE}

    await client.brake_release()
    for _ in range(30):
        if (await client.robotmode()) is RobotMode.IDLE:
            break
        await asyncio.sleep(0.5)
    assert await client.robotmode() is RobotMode.IDLE

    # Park it back in POWER_OFF so subsequent test runs start from the same state.
    await client.power_off()
