#!/usr/bin/env python3
"""Stream TCP pose + joint positions at 10 Hz for 30 s.

Run:
    ROBOT_IP=127.0.0.1 python examples/telemetry_stream.py
"""

from __future__ import annotations

import sys
import time

from ie_ur5e.connection import load_config
from ie_ur5e.motion import MotionError, UR5eMotion


def main(duration_s: float = 30.0, hz: float = 10.0) -> int:
    cfg = load_config()
    period = 1.0 / hz
    deadline = time.monotonic() + duration_s

    try:
        with UR5eMotion(cfg.host_ip, cfg) as m:
            print(
                f"Streaming TCP + joints from {cfg.host_ip} at {hz:.0f} Hz "
                f"for {duration_s:.0f}s (Ctrl-C to abort)"
            )
            n = 0
            while time.monotonic() < deadline:
                t0 = time.monotonic()
                tcp = m.get_tcp_pose()
                q = m.get_joint_positions()
                snap = m.monitor.latest()  # type: ignore[union-attr]
                bits = f"0x{snap.bits:04x}" if snap else "----"
                print(
                    f"[{n:04d}] tcp=("
                    f"{tcp.x:+.3f},{tcp.y:+.3f},{tcp.z:+.3f}) "
                    f"q=[{','.join(f'{j:+.3f}' for j in q)}] "
                    f"safety_bits={bits}"
                )
                n += 1
                slack = period - (time.monotonic() - t0)
                if slack > 0:
                    time.sleep(slack)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
    except MotionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
