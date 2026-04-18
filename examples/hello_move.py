#!/usr/bin/env python3
"""Hello-move demo: home → 200x200mm square @ z=0.2m → home.

Run:
    ROBOT_IP=127.0.0.1 python examples/hello_move.py     # against URSim
    ROBOT_IP=192.168.1.10 python examples/hello_move.py  # against the arm

Aborts loud if URControl isn't accepting RTDE (e.g. URSim NO_CONTROLLER on
Apple-Silicon emulation, or the arm is powered off).
"""

from __future__ import annotations

import sys

from ie_ur5e.connection import load_config
from ie_ur5e.motion import MotionError, UR5eMotion


def main() -> int:
    cfg = load_config()
    print(f"Connecting to {cfg.host_ip} (RTDE @ {cfg.rtde_frequency} Hz)…")

    try:
        with UR5eMotion(cfg.host_ip, cfg) as m:
            print(f"  safety: {m.monitor.latest()}")  # type: ignore[union-attr]

            print(f"  homing → {cfg.home_joints_rad}")
            m.move_j(cfg.home_joints_rad, speed=0.5, accel=1.0)

            here = m.get_tcp_pose()
            print(f"  TCP at home: x={here.x:+.3f} y={here.y:+.3f} z={here.z:+.3f}")

            # Walk a 200x200 mm square 200 mm above the base, keeping the
            # orientation we landed in (no wrist-flip).
            z = 0.20
            cx, cy = -0.20, -0.40  # 400 mm in front of base, 200 mm to the left
            half = 0.10
            corners = [
                [cx - half, cy - half, z, here.rx, here.ry, here.rz],
                [cx + half, cy - half, z, here.rx, here.ry, here.rz],
                [cx + half, cy + half, z, here.rx, here.ry, here.rz],
                [cx - half, cy + half, z, here.rx, here.ry, here.rz],
                [cx - half, cy - half, z, here.rx, here.ry, here.rz],  # close loop
            ]
            for i, p in enumerate(corners, 1):
                print(f"  corner {i}/5 → x={p[0]:+.3f} y={p[1]:+.3f} z={p[2]:+.3f}")
                m.move_l(p, speed=0.10, accel=0.5)

            print("  back to home")
            m.move_j(cfg.home_joints_rad, speed=0.5, accel=1.0)
            print("Done.")
    except MotionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
