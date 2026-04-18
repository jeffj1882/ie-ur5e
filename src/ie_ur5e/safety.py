"""RTDE-driven safety monitor with callbacks and a 100ms staleness watchdog.

A background thread polls `getSafetyStatusBits()` and `getRobotMode()` at
the RTDE frequency (default 125 Hz) and dispatches typed events when bits
change. If the polling thread can't read fresh state for >100ms it raises
a `WatchdogTripped` flag that motion code consults *before every command*.
"""

from __future__ import annotations

import contextlib
import enum
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


# Bit indices per the UR e-Series RTDE manual, "Safety Status Bits" vector.
class SafetyBit(enum.IntEnum):
    NORMAL_MODE = 0
    REDUCED_MODE = 1
    PROTECTIVE_STOPPED = 2
    RECOVERY_MODE = 3
    SAFEGUARD_STOPPED = 4
    SYSTEM_EMERGENCY_STOPPED = 5
    ROBOT_EMERGENCY_STOPPED = 6
    EMERGENCY_STOPPED = 7
    VIOLATION = 8
    FAULT = 9
    STOPPED_DUE_TO_SAFETY = 10


# Robot modes from getRobotMode() — distinct from the Dashboard's text-mode reply.
class SafeRobotMode(enum.IntEnum):
    NO_CONTROLLER = -1
    DISCONNECTED = 0
    CONFIRM_SAFETY = 1
    BOOTING = 2
    POWER_OFF = 3
    POWER_ON = 4
    IDLE = 5
    BACKDRIVE = 6
    RUNNING = 7
    UPDATING_FIRMWARE = 8


@dataclass(frozen=True)
class SafetySnapshot:
    bits: int
    mode: int
    timestamp: float

    def has(self, bit: SafetyBit) -> bool:
        return bool(self.bits & (1 << bit.value))

    @property
    def is_normal(self) -> bool:
        return self.has(SafetyBit.NORMAL_MODE) and not (
            self.has(SafetyBit.PROTECTIVE_STOPPED)
            or self.has(SafetyBit.SAFEGUARD_STOPPED)
            or self.has(SafetyBit.EMERGENCY_STOPPED)
            or self.has(SafetyBit.SYSTEM_EMERGENCY_STOPPED)
            or self.has(SafetyBit.ROBOT_EMERGENCY_STOPPED)
            or self.has(SafetyBit.VIOLATION)
            or self.has(SafetyBit.FAULT)
        )


class WatchdogTripped(RuntimeError):
    """Raised when motion is attempted while the safety watchdog is in fault."""


class NotInNormalMode(RuntimeError):
    """Raised when motion is requested but safety is not NORMAL."""


class _RTDEReceiveLike(Protocol):
    """Subset of ur_rtde.RTDEReceiveInterface that the monitor uses."""

    def getSafetyStatusBits(self) -> int: ...
    def getRobotMode(self) -> int: ...
    def isConnected(self) -> bool: ...


Listener = Callable[[SafetySnapshot], None]


@dataclass
class SafetyMonitor:
    """Polls a `_RTDEReceiveLike` and fires typed callbacks on transitions.

    Acts as the single source of truth for "is it safe to issue motion?".
    Motion code MUST call `assert_safe()` before sending any command.
    """

    receive: _RTDEReceiveLike
    frequency_hz: int = 125
    watchdog_ms: int = 100

    _on_protective_stop: list[Listener] = field(default_factory=list)
    _on_emergency_stop: list[Listener] = field(default_factory=list)
    _on_safeguard_stop: list[Listener] = field(default_factory=list)
    _on_fault: list[Listener] = field(default_factory=list)

    _last: SafetySnapshot | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _watchdog_tripped: bool = False
    _last_ok_ts: float = 0.0

    # ── Subscriptions ──────────────────────────────────────────────────────
    def on_protective_stop(self, cb: Listener) -> None:
        self._on_protective_stop.append(cb)

    def on_emergency_stop(self, cb: Listener) -> None:
        self._on_emergency_stop.append(cb)

    def on_safeguard_stop(self, cb: Listener) -> None:
        self._on_safeguard_stop.append(cb)

    def on_fault(self, cb: Listener) -> None:
        self._on_fault.append(cb)

    # ── Lifecycle ──────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._watchdog_tripped = False
        self._last_ok_ts = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="ur5e-safety", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ── Query ──────────────────────────────────────────────────────────────
    def latest(self) -> SafetySnapshot | None:
        with self._lock:
            return self._last

    def watchdog_tripped(self) -> bool:
        return self._watchdog_tripped

    def assert_safe(self) -> None:
        """Raise unless the latest snapshot says NORMAL and watchdog is healthy."""
        if self._watchdog_tripped:
            raise WatchdogTripped(
                f"RTDE silent for >{self.watchdog_ms}ms — refusing to issue motion"
            )
        snap = self.latest()
        if snap is None:
            raise WatchdogTripped("safety monitor has no snapshot yet")
        if not snap.is_normal:
            raise NotInNormalMode(
                f"safety not NORMAL (bits=0x{snap.bits:04x}, mode={snap.mode}) — "
                "human acknowledgment required (see dashboard.unlock_protective_stop)"
            )

    # ── Internal ───────────────────────────────────────────────────────────
    def _run(self) -> None:
        period = 1.0 / max(1, self.frequency_hz)
        watchdog_s = self.watchdog_ms / 1000.0
        prev: SafetySnapshot | None = None
        while not self._stop.is_set():
            now = time.monotonic()
            try:
                if not self.receive.isConnected():
                    self._mark_stale(now, watchdog_s)
                    self._stop.wait(period)
                    continue
                bits = int(self.receive.getSafetyStatusBits())
                mode = int(self.receive.getRobotMode())
            except Exception:
                self._mark_stale(now, watchdog_s)
                self._stop.wait(period)
                continue

            snap = SafetySnapshot(bits=bits, mode=mode, timestamp=now)
            with self._lock:
                self._last = snap
            self._last_ok_ts = now
            self._watchdog_tripped = False
            self._dispatch(prev, snap)
            prev = snap
            self._stop.wait(period)

    def _mark_stale(self, now: float, watchdog_s: float) -> None:
        if now - self._last_ok_ts > watchdog_s and not self._watchdog_tripped:
            self._watchdog_tripped = True
            stale = SafetySnapshot(bits=0, mode=int(SafeRobotMode.DISCONNECTED), timestamp=now)
            for cb in self._on_fault:
                _safe_call(cb, stale)

    def _dispatch(self, prev: SafetySnapshot | None, cur: SafetySnapshot) -> None:
        events = (
            (SafetyBit.PROTECTIVE_STOPPED, self._on_protective_stop),
            (SafetyBit.EMERGENCY_STOPPED, self._on_emergency_stop),
            (SafetyBit.SAFEGUARD_STOPPED, self._on_safeguard_stop),
            (SafetyBit.FAULT, self._on_fault),
        )
        for bit, callbacks in events:
            now = cur.has(bit)
            was = prev is not None and prev.has(bit)
            if now and not was:
                for cb in callbacks:
                    _safe_call(cb, cur)


def _safe_call(cb: Listener, snap: SafetySnapshot) -> None:
    # Callbacks must never crash the monitor thread.
    with contextlib.suppress(Exception):
        cb(snap)
