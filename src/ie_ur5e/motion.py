"""ur_rtde wrapper providing safe `move_j` / `move_l` and freedrive teachmode.

Hard rules enforced here:
- Connection is brokered via the `UR5eMotion(host, config)` context manager.
- A `SafetyMonitor` runs the entire time the connection is open. Every motion
  call invokes `monitor.assert_safe()` first; a non-NORMAL state or a
  watchdog trip raises immediately. There are NO silent retries on safety
  events — protective/emergency stops require explicit human ack via
  `dashboard.unlock_protective_stop()` or the pendant.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Self

from rtde_control import RTDEControlInterface
from rtde_receive import RTDEReceiveInterface

from ie_ur5e.connection import RobotConfig, load_config
from ie_ur5e.safety import SafetyMonitor


class MotionError(RuntimeError):
    """Generic motion failure (RTDE returned False, etc.)."""


@dataclass(frozen=True)
class TCPPose:
    x: float
    y: float
    z: float
    rx: float
    ry: float
    rz: float

    @classmethod
    def from_list(cls, p: list[float]) -> TCPPose:
        return cls(*p[:6])

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z, self.rx, self.ry, self.rz]


class UR5eMotion:
    """Safety-gated RTDE motion wrapper. Use as a context manager."""

    def __init__(
        self,
        host: str | None = None,
        config: RobotConfig | None = None,
        *,
        rtde_frequency: int | None = None,
    ) -> None:
        self.config = config or load_config()
        self.host = host or self.config.host_ip
        self.frequency = rtde_frequency or self.config.rtde_frequency

        self._control: RTDEControlInterface | None = None
        self._receive: RTDEReceiveInterface | None = None
        self.monitor: SafetyMonitor | None = None

    # ── Context manager ─────────────────────────────────────────────────────
    def __enter__(self) -> Self:
        try:
            self._receive = RTDEReceiveInterface(self.host, frequency=float(self.frequency))
            self._control = RTDEControlInterface(self.host, frequency=float(self.frequency))
        except RuntimeError as e:
            # ur_rtde raises RuntimeError when URControl isn't accepting RTDE
            # connections. Most common cause: NO_CONTROLLER on URSim, or
            # robot is not powered on yet.
            self._cleanup()
            raise MotionError(
                f"failed to connect to UR controller at {self.host}: {e} "
                "(power on the robot via the pendant or `ie-ur5e-dash power-on`)"
            ) from e

        self.monitor = SafetyMonitor(self._receive, frequency_hz=self.frequency)
        self.monitor.start()

        # Apply payload + TCP from config so callers don't have to remember.
        if self.config.payload_kg > 0:
            self._control.setPayload(self.config.payload_kg, [0.0, 0.0, 0.0])
        if any(self.config.tcp_offset):
            self._control.setTcp(self.config.tcp_offset)
        return self

    def __exit__(self, *exc: object) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        if self.monitor:
            self.monitor.stop()
            self.monitor = None
        if self._control is not None:
            with contextlib.suppress(Exception):
                self._control.stopScript()
            with contextlib.suppress(Exception):
                self._control.disconnect()
            self._control = None
        if self._receive is not None:
            with contextlib.suppress(Exception):
                self._receive.disconnect()
            self._receive = None

    # ── Motion ──────────────────────────────────────────────────────────────
    def move_j(self, joints_rad: list[float], speed: float = 0.5, accel: float = 1.0) -> None:
        """Joint-space move. Speed in rad/s, accel in rad/s². Blocking."""
        self._require_safe()
        if len(joints_rad) != 6:
            raise ValueError("joints_rad must have 6 entries")
        ok = self._control.moveJ(list(joints_rad), float(speed), float(accel))  # type: ignore[union-attr]
        if not ok:
            raise MotionError(f"moveJ rejected: joints={joints_rad}")

    def move_l(self, pose: list[float], speed: float = 0.25, accel: float = 1.2) -> None:
        """Cartesian linear move. pose=[x,y,z,rx,ry,rz]. speed m/s, accel m/s²."""
        self._require_safe()
        if len(pose) != 6:
            raise ValueError("pose must have 6 entries [x,y,z,rx,ry,rz]")
        ok = self._control.moveL(list(pose), float(speed), float(accel))  # type: ignore[union-attr]
        if not ok:
            raise MotionError(f"moveL rejected: pose={pose}")

    # ── State ───────────────────────────────────────────────────────────────
    def get_tcp_pose(self) -> TCPPose:
        return TCPPose.from_list(self._receive.getActualTCPPose())  # type: ignore[union-attr]

    def get_joint_positions(self) -> list[float]:
        return list(self._receive.getActualQ())  # type: ignore[union-attr]

    def get_tcp_force(self) -> list[float]:
        return list(self._receive.getActualTCPForce())  # type: ignore[union-attr]

    def is_steady(self, threshold: float = 0.01) -> bool:
        velocities = self._receive.getActualQd()  # type: ignore[union-attr]
        return all(abs(v) < threshold for v in velocities)

    def set_payload(self, mass_kg: float, cog_xyz: list[float]) -> None:
        if not self._control.setPayload(float(mass_kg), list(cog_xyz)):  # type: ignore[union-attr]
            raise MotionError("setPayload rejected")

    def set_tcp(self, pose: list[float]) -> None:
        if len(pose) != 6:
            raise ValueError("pose must have 6 entries")
        if not self._control.setTcp(list(pose)):  # type: ignore[union-attr]
            raise MotionError("setTcp rejected")

    @contextlib.contextmanager
    def freedrive(self) -> Iterator[None]:
        """Enable teachmode (freedrive); always disabled on exit."""
        self._require_safe()
        if not self._control.teachMode():  # type: ignore[union-attr]
            raise MotionError("teachMode failed to engage")
        try:
            yield
        finally:
            with contextlib.suppress(Exception):
                self._control.endTeachMode()  # type: ignore[union-attr]

    # ── Internal ────────────────────────────────────────────────────────────
    def _require_safe(self) -> None:
        if self.monitor is None or self._control is None:
            raise MotionError("UR5eMotion not entered as a context manager")
        self.monitor.assert_safe()
