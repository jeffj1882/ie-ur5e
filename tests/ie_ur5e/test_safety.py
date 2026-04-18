"""Offline unit tests for SafetyMonitor — no RTDE required."""

from __future__ import annotations

import time

import pytest

from ie_ur5e.safety import (
    NotInNormalMode,
    SafetyBit,
    SafetyMonitor,
    SafetySnapshot,
    WatchdogTripped,
)


class FakeReceive:
    """Stand-in for RTDEReceiveInterface. Scriptable bits/mode/connection."""

    def __init__(self, bits: int = 1, mode: int = 5, connected: bool = True) -> None:
        self.bits = bits
        self.mode = mode
        self.connected = connected
        self.reads = 0
        self.raise_next = False

    def getSafetyStatusBits(self) -> int:
        self.reads += 1
        if self.raise_next:
            self.raise_next = False
            raise ConnectionError("simulated RTDE drop")
        return self.bits

    def getRobotMode(self) -> int:
        return self.mode

    def isConnected(self) -> bool:
        return self.connected


# ── Pure snapshot logic ─────────────────────────────────────────────────────
def test_snapshot_is_normal_requires_normal_bit() -> None:
    assert SafetySnapshot(bits=1 << SafetyBit.NORMAL_MODE, mode=5, timestamp=0).is_normal
    assert not SafetySnapshot(bits=0, mode=5, timestamp=0).is_normal


def test_snapshot_is_normal_rejects_protective_stop() -> None:
    bits = (1 << SafetyBit.NORMAL_MODE) | (1 << SafetyBit.PROTECTIVE_STOPPED)
    assert not SafetySnapshot(bits=bits, mode=5, timestamp=0).is_normal


# ── SafetyMonitor ───────────────────────────────────────────────────────────
def test_assert_safe_raises_before_first_read() -> None:
    fake = FakeReceive()
    mon = SafetyMonitor(fake, frequency_hz=200)
    with pytest.raises(WatchdogTripped):
        mon.assert_safe()


def test_assert_safe_passes_when_normal() -> None:
    fake = FakeReceive(bits=1 << SafetyBit.NORMAL_MODE)
    mon = SafetyMonitor(fake, frequency_hz=200)
    mon.start()
    try:
        _wait_for_snapshot(mon)
        mon.assert_safe()
    finally:
        mon.stop()


def test_assert_safe_raises_when_protective_stop() -> None:
    bits = (1 << SafetyBit.NORMAL_MODE) | (1 << SafetyBit.PROTECTIVE_STOPPED)
    fake = FakeReceive(bits=bits)
    mon = SafetyMonitor(fake, frequency_hz=200)
    mon.start()
    try:
        _wait_for_snapshot(mon)
        with pytest.raises(NotInNormalMode):
            mon.assert_safe()
    finally:
        mon.stop()


def test_protective_stop_callback_fires_on_transition() -> None:
    fake = FakeReceive(bits=1 << SafetyBit.NORMAL_MODE)
    mon = SafetyMonitor(fake, frequency_hz=200)
    fired: list[SafetySnapshot] = []
    mon.on_protective_stop(fired.append)
    mon.start()
    try:
        _wait_for_snapshot(mon)
        fake.bits = (1 << SafetyBit.NORMAL_MODE) | (1 << SafetyBit.PROTECTIVE_STOPPED)
        _wait_until(lambda: len(fired) == 1, timeout=1.0)
        assert fired[0].has(SafetyBit.PROTECTIVE_STOPPED)
    finally:
        mon.stop()


def test_watchdog_trips_on_rtde_drop() -> None:
    fake = FakeReceive(bits=1 << SafetyBit.NORMAL_MODE)
    mon = SafetyMonitor(fake, frequency_hz=500, watchdog_ms=50)
    mon.start()
    try:
        _wait_for_snapshot(mon)
        fake.connected = False
        _wait_until(mon.watchdog_tripped, timeout=1.0)
        with pytest.raises(WatchdogTripped):
            mon.assert_safe()
    finally:
        mon.stop()


def test_fault_callback_fires_on_watchdog() -> None:
    fake = FakeReceive(bits=1 << SafetyBit.NORMAL_MODE)
    mon = SafetyMonitor(fake, frequency_hz=500, watchdog_ms=50)
    fired: list[SafetySnapshot] = []
    mon.on_fault(fired.append)
    mon.start()
    try:
        _wait_for_snapshot(mon)
        fake.connected = False
        _wait_until(lambda: len(fired) >= 1, timeout=1.0)
    finally:
        mon.stop()


def test_transient_read_exception_does_not_crash_monitor() -> None:
    fake = FakeReceive(bits=1 << SafetyBit.NORMAL_MODE)
    mon = SafetyMonitor(fake, frequency_hz=500)
    mon.start()
    try:
        _wait_for_snapshot(mon)
        fake.raise_next = True
        # Give the monitor a tick to absorb the exception and keep running.
        time.sleep(0.05)
        _wait_for_snapshot(mon)
        assert mon.latest() is not None
    finally:
        mon.stop()


def _wait_for_snapshot(mon: SafetyMonitor, timeout: float = 1.0) -> None:
    _wait_until(lambda: mon.latest() is not None, timeout=timeout)


def _wait_until(predicate, timeout: float) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition not met within timeout")
