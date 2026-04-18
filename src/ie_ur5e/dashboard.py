"""Async client for the UR Dashboard Server on TCP :29999.

The Dashboard protocol is newline-terminated ASCII, one command per line.
See the "Dashboard Server" section of the Universal Robots e-Series manual
(commands that work on PolyScope 5.x — UR5e).
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
from dataclasses import dataclass
from typing import Self

_BANNER_PREFIX = b"Connected:"
_DEFAULT_TIMEOUT = 5.0


class DashboardError(Exception):
    """Base for dashboard client errors."""


class RobotNotInRemoteControl(DashboardError):
    """The robot is in local control; Dashboard write commands are rejected."""


class ProtectiveStopActive(DashboardError):
    """Robot is currently in protective stop."""


class EmergencyStopActive(DashboardError):
    """Robot is currently in emergency stop."""


class ProgramNotLoaded(DashboardError):
    """The requested program could not be loaded."""


class DashboardTimeout(DashboardError):
    """Socket read/write exceeded the configured timeout."""


class RobotMode(enum.StrEnum):
    NO_CONTROLLER = "NO_CONTROLLER"
    DISCONNECTED = "DISCONNECTED"
    CONFIRM_SAFETY = "CONFIRM_SAFETY"
    BOOTING = "BOOTING"
    POWER_OFF = "POWER_OFF"
    POWER_ON = "POWER_ON"
    IDLE = "IDLE"
    BACKDRIVE = "BACKDRIVE"
    RUNNING = "RUNNING"
    UPDATING_FIRMWARE = "UPDATING_FIRMWARE"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> RobotMode:
        return cls.UNKNOWN


class SafetyStatus(enum.StrEnum):
    NORMAL = "NORMAL"
    REDUCED = "REDUCED"
    PROTECTIVE_STOP = "PROTECTIVE_STOP"
    RECOVERY = "RECOVERY"
    SAFEGUARD_STOP = "SAFEGUARD_STOP"
    SYSTEM_EMERGENCY_STOP = "SYSTEM_EMERGENCY_STOP"
    ROBOT_EMERGENCY_STOP = "ROBOT_EMERGENCY_STOP"
    VIOLATION = "VIOLATION"
    FAULT = "FAULT"
    AUTOMATIC_MODE_SAFEGUARD_STOP = "AUTOMATIC_MODE_SAFEGUARD_STOP"
    SYSTEM_THREE_POSITION_ENABLING_STOP = "SYSTEM_THREE_POSITION_ENABLING_STOP"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def _missing_(cls, value: object) -> SafetyStatus:
        return cls.UNKNOWN


@dataclass(frozen=True)
class RawResponse:
    line: str

    @property
    def lower(self) -> str:
        return self.line.lower()


class DashboardClient:
    """One-shot async Dashboard client. Use as an async context manager."""

    def __init__(self, host: str, port: int = 29999, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
            # Consume banner so the next readline sees a real reply.
            banner = await asyncio.wait_for(self._reader.readline(), timeout=self.timeout)
            if not banner.startswith(_BANNER_PREFIX):
                raise DashboardError(f"unexpected banner: {banner!r}")
        except TimeoutError as e:
            raise DashboardTimeout(f"connect to {self.host}:{self.port} timed out") from e

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await self._writer.wait_closed()
        self._reader = None
        self._writer = None

    # ── Low-level I/O ────────────────────────────────────────────────────────
    async def _send(self, cmd: str) -> str:
        if self._writer is None or self._reader is None:
            raise DashboardError("client not connected")
        async with self._lock:
            try:
                self._writer.write(f"{cmd}\n".encode("ascii"))
                await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)
                line = await asyncio.wait_for(self._reader.readline(), timeout=self.timeout)
            except TimeoutError as e:
                raise DashboardTimeout(f"{cmd!r} timed out after {self.timeout:.1f}s") from e
            if not line:
                raise DashboardError(f"{cmd!r}: connection closed by server")
            return line.decode("ascii", errors="replace").strip()

    # ── Typed commands ───────────────────────────────────────────────────────
    async def robotmode(self) -> RobotMode:
        reply = await self._send("robotmode")
        token = reply.split(":", 1)[-1].strip().upper()
        return RobotMode(token)

    async def safetystatus(self) -> SafetyStatus:
        reply = await self._send("safetystatus")
        token = reply.split(":", 1)[-1].strip().upper()
        return SafetyStatus(token)

    async def power_on(self) -> str:
        return self._check_remote(await self._send("power on"))

    async def power_off(self) -> str:
        return self._check_remote(await self._send("power off"))

    async def brake_release(self) -> str:
        return self._check_remote(await self._send("brake release"))

    async def unlock_protective_stop(self) -> str:
        reply = self._check_remote(await self._send("unlock protective stop"))
        if "not currently in" in reply.lower() or "can not" in reply.lower():
            # Server said there's nothing to unlock; callers can ignore or log.
            return reply
        return reply

    async def popup(self, msg: str) -> str:
        # Dashboard: `popup <msg>` — msg is free-form until newline.
        msg = msg.replace("\n", " ")
        return await self._send(f"popup {msg}")

    async def close_popup(self) -> str:
        return await self._send("close popup")

    async def play(self) -> str:
        reply = self._check_remote(await self._send("play"))
        if reply.lower().startswith("failed"):
            raise DashboardError(reply)
        return reply

    async def stop(self) -> str:
        return self._check_remote(await self._send("stop"))

    async def pause(self) -> str:
        return self._check_remote(await self._send("pause"))

    async def load(self, program: str) -> str:
        reply = self._check_remote(await self._send(f"load {program}"))
        low = reply.lower()
        if low.startswith("file not found") or low.startswith("error while loading"):
            raise ProgramNotLoaded(reply)
        return reply

    async def get_loaded_program(self) -> str | None:
        reply = await self._send("get loaded program")
        if reply.lower().startswith("no program loaded"):
            return None
        # "Loaded program: /ursim/programs/foo.urp"
        return reply.split(":", 1)[-1].strip()

    async def is_in_remote_control(self) -> bool:
        reply = await self._send("is in remote control")
        return reply.strip().lower() == "true"

    # ── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _check_remote(reply: str) -> str:
        low = reply.lower()
        if "not in remote" in low or "controlled by teach" in low:
            raise RobotNotInRemoteControl(reply)
        return reply
